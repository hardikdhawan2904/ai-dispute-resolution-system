"""
Agent 3 — WOA (Workflow Orchestration Agent)

Job: Read the combined Agent 1 + Agent 2 results from the database, pre-run
     6 deterministic orchestration tools, pass results to the LLM for synthesis,
     and return a workflow plan that drives the multi-agent routing system.

DB interaction:
  - Reads case + investigation fields from dispute_cases by case_id
  - All tools are pre-run server-side (same pattern as Agent 2)
  - LLM synthesises from pre-computed tool results

Tools:
  evaluate_case_complexity        → orchestration complexity level
  determine_required_agents       → specialist agents needed
  recommend_workflow_path         → ordered execution sequence
  assess_escalation_need          → escalation level and triggers
  estimate_workload               → analyst hours + seniority
  determine_next_execution_step   → immediate next agent to run
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.orchestration_agent.graph import orchestration_graph
from agents.orchestration_agent.state import OrchestrationAgentState
from agents.orchestration_agent.tools import (
    evaluate_case_complexity,
    determine_required_agents,
    recommend_workflow_path,
    assess_escalation_need,
    estimate_workload,
    determine_next_execution_step,
)
from prompts.orchestration_prompts import SYSTEM_PROMPT
from utils.logger import agent_logger
from utils.helpers import utc_now_iso


def _read_case_from_db(case_id: str) -> dict:
    """Read combined Agent 1 + Agent 2 results from dispute_cases by case_id."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found in database")
        agent_logger.info(f"WOA reading case {case_id} from database")
        return {
            "case_id":                case.case_id,
            "customer_id":            case.customer_id,
            "amount":                 case.amount,
            "currency":               case.currency,
            "dispute_category":       case.dispute_category or "Other",
            "fraud_suspicion":        case.fraud_suspicion,
            "fraud_selected":         case.fraud_selected,
            "risk_tags":              case.risk_tags or [],
            "priority":               case.priority or "MEDIUM",
            "confidence_score":       case.confidence_score or 0.0,
            "evidence_match":         case.evidence_match,
            "requires_manual_review": case.requires_manual_review,
            "investigation_plan":     case.investigation_plan or {},
            "workflow_plan":          getattr(case, "workflow_plan", None),
        }
    finally:
        db.close()


def _run_tools(case_id: str) -> tuple:
    """Pre-run all 6 tools in parallel — each is an independent DB read."""
    tool_defs = [
        ("evaluate_case_complexity",      evaluate_case_complexity),
        ("determine_required_agents",     determine_required_agents),
        ("recommend_workflow_path",       recommend_workflow_path),
        ("assess_escalation_need",        assess_escalation_need),
        ("estimate_workload",             estimate_workload),
        ("determine_next_execution_step", determine_next_execution_step),
    ]

    def _run_one(name: str, fn) -> tuple:
        try:
            return name, fn.invoke({"case_id": case_id})
        except Exception as exc:
            agent_logger.warning(f"WOA tool {name} failed for {case_id}: {exc}")
            return name, f"{name.upper()}\n  Error: Tool execution failed — {exc}"

    results: dict = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_run_one, name, fn): name for name, fn in tool_defs}
        for fut in as_completed(futures):
            name, result = fut.result()
            results[name] = result

    # Preserve canonical order for the human message
    used = [name for name, _ in tool_defs if name in results]
    return results, used


def _build_human_message(case_input: dict, tool_results: dict) -> str:
    inv_plan    = case_input.get("investigation_plan") or {}
    inv_queue   = inv_plan.get("recommended_queue", "N/A") if isinstance(inv_plan, dict) else "N/A"
    inv_complex = inv_plan.get("investigation_complexity", "N/A") if isinstance(inv_plan, dict) else "N/A"
    manual_req  = inv_plan.get("manual_review_required", False) if isinstance(inv_plan, dict) else False
    risk_tags   = case_input.get("risk_tags") or []
    tags_str    = ", ".join(risk_tags) if risk_tags else "None"

    _TOOL_ORDER = [
        "evaluate_case_complexity",
        "determine_required_agents",
        "recommend_workflow_path",
        "assess_escalation_need",
        "estimate_workload",
        "determine_next_execution_step",
    ]

    tool_section = "\n\n## PRE-COMPUTED TOOL RESULTS\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    return (
        "## Combined Agent 1 + Agent 2 Output (read from database)\n"
        f"Case ID                   : {case_input.get('case_id', 'N/A')}\n"
        f"Dispute Category          : {case_input.get('dispute_category', 'N/A')}\n"
        f"Fraud Suspicion (AI)      : {case_input.get('fraud_suspicion', False)}\n"
        f"Fraud Claimed (Customer)  : {case_input.get('fraud_selected', False)}\n"
        f"Amount                    : {case_input.get('currency', 'INR')} {case_input.get('amount', 0)}\n"
        f"Priority                  : {case_input.get('priority', 'N/A')}\n"
        f"Confidence Score          : {case_input.get('confidence_score', 0.0)}\n"
        f"Risk Tags                 : {tags_str}\n"
        f"Evidence Match            : {case_input.get('evidence_match')}\n"
        "\n## Agent 2 Investigation Summary\n"
        f"Recommended Queue         : {inv_queue}\n"
        f"Investigation Complexity  : {inv_complex}\n"
        f"Manual Review Required    : {manual_req}\n"
        + tool_section
    )


def run_orchestration_agent(case_id: str) -> dict:
    """
    Read case from DB, pre-run all 6 orchestration tools, synthesise via LLM,
    return a complete workflow plan.

    Always returns a valid dict — falls back gracefully if the graph fails.
    """
    from agents.orchestration_agent.nodes.pipeline import _fallback_output
    from agents.orchestration_agent.config import get_llm_config

    start_time = time.time()

    try:
        case_input = _read_case_from_db(case_id)
    except Exception as exc:
        agent_logger.error(f"WOA DB read failed for {case_id}: {exc}", exc_info=True)
        return {
            "case_id":               case_id,
            "workflow_complexity":   "MEDIUM",
            "required_agents":       [],
            "workflow_path":         [],
            "workflow_status":       "READY",
            "next_agent":            None,
            "remaining_agents":      [],
            "completed_agents":      [],
            "escalation_required":   False,
            "escalation_level":      None,
            "manual_review_required": True,
            "estimated_investigation_hours": 2,
            "analyst_level":         "STANDARD",
            "workflow_reasoning":    [f"WOA DB read failed: {exc}. Manual review required."],
            "tool_decisions":        [],
            "tools_used":            [],
            "agent_metadata":        {},
            "metrics":               {},
            "workflow_execution_id": f"WF-DBERR-{uuid.uuid4().hex[:8].upper()}",
            "workflow_version":      "1.0",
            "fallback_mode":         True,
            "failure_reason":        "DB_READ_FAILURE",
            "created_at":            utc_now_iso(),
        }

    # Pre-run all 6 tools
    tool_results, tools_used = _run_tools(case_id)

    initial: OrchestrationAgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_human_message(case_input, tool_results)),
        ],
        "case_input":       case_input,
        "tool_results":     tool_results,
        "final_output":     {},
        "error":            None,
        "tools_used":       tools_used,
        "agent_metadata":   {},
        "metrics":          {},
        "agent_start_time": start_time,
    }

    try:
        result = orchestration_graph.invoke(initial, config={"recursion_limit": 4})
        return result["final_output"]
    except Exception as exc:
        agent_logger.error(f"WOA graph failed for {case_id}: {exc}", exc_info=True)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        cfg = get_llm_config()
        meta = {
            "agent_name":            "Workflow Orchestration Agent",
            "agent_version":         "1.0.0",
            "model":                 cfg["model"],
            "execution_timestamp":   utc_now_iso(),
            "execution_duration_ms": duration_ms,
        }
        metrics = {
            "total_duration_ms": duration_ms,
            "llm_calls":  0,
            "tool_calls": len(tools_used),
            "retry_count": 3,
        }
        return _fallback_output(case_input, case_id, tools_used, meta, metrics)

