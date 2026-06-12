"""
Agent 4 — EIA (Evidence Intelligence Agent)

Job: Read the combined case data (Agent 1 + Agent 2 + Agent 3 context) from the
     database, pre-run 5 deterministic evidence tools, pass results to the LLM for
     synthesis, and return a structured evidence assessment: completeness, strength,
     consistency, missing documents, and recommended document requests.

Invocation:
  - Called by the dispute workflow when WOA routes to EVIDENCE_AGENT
  - Called directly via the ops API (manual evidence review trigger)
  - Never runs automatically — WOA decides whether evidence review is needed

DB interaction:
  - Reads case + investigation_plan + workflow_plan from dispute_cases by case_id
  - Reads document_requests for the case
  - Reads transactions for consistency check
  - All tools are pre-run server-side (same pattern as Agent 2 and 3)
  - LLM synthesises from pre-computed tool results — no runtime tool calls

Tools:
  evaluate_evidence_completeness  → completeness score and missing document list
  identify_missing_evidence       → unfulfilled required documents
  validate_evidence_consistency   → transaction detail consistency check
  assess_evidence_strength        → overall evidence strength (HIGH/MEDIUM/LOW)
  determine_next_document_request → next specific document to request
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.evidence_agent.graph import evidence_graph
from agents.evidence_agent.state import EvidenceAgentState
from agents.evidence_agent.tools import (
    evaluate_evidence_completeness,
    identify_missing_evidence,
    validate_evidence_consistency,
    assess_evidence_strength,
    determine_next_document_request,
)
from prompts.evidence_prompts import SYSTEM_PROMPT
from utils.logger import agent_logger
from utils.helpers import utc_now_iso


def _read_case_from_db(case_id: str) -> dict:
    """Read combined case data (Agent 1 + Agent 2 context) from dispute_cases by case_id."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found in database")
        agent_logger.info(f"EIA reading case {case_id} from database")
        return {
            "case_id":            case.case_id,
            "customer_id":        case.customer_id,
            "transaction_id":     case.transaction_id,
            "transaction_type":   case.transaction_type or "",
            "merchant":           case.merchant or "",
            "amount":             float(case.amount or 0),
            "currency":           case.currency or "INR",
            "transaction_date":   case.transaction_date or "",
            "dispute_category":   case.dispute_category or "Other",
            "fraud_suspicion":    case.fraud_suspicion or False,
            "evidence_match":     case.evidence_match,
            "evidence_match_note": case.evidence_match_note or "",
            "risk_tags":          case.risk_tags or [],
            "priority":           case.priority or "MEDIUM",
            "investigation_plan": case.investigation_plan or {},
            "workflow_plan":      case.workflow_plan or {},
        }
    finally:
        db.close()


def _run_tools(case_id: str) -> tuple:
    """Pre-run all 5 evidence tools in parallel — each is an independent DB read."""
    tool_defs = [
        ("evaluate_evidence_completeness",  evaluate_evidence_completeness),
        ("identify_missing_evidence",       identify_missing_evidence),
        ("validate_evidence_consistency",   validate_evidence_consistency),
        ("assess_evidence_strength",        assess_evidence_strength),
        ("determine_next_document_request", determine_next_document_request),
    ]

    def _run_one(name: str, fn) -> tuple:
        try:
            return name, fn.invoke({"case_id": case_id})
        except Exception as exc:
            agent_logger.warning(f"EIA tool {name} failed for {case_id}: {exc}")
            return name, f"{name.upper()}\n  Error: Tool execution failed — {exc}"

    results: dict = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_run_one, name, fn): name for name, fn in tool_defs}
        for fut in as_completed(futures):
            name, result = fut.result()
            results[name] = result

    used = [name for name, _ in tool_defs if name in results]
    return results, used


def _build_human_message(case_input: dict, tool_results: dict) -> str:
    inv_plan     = case_input.get("investigation_plan") or {}
    inv_queue    = inv_plan.get("recommended_queue", "N/A") if isinstance(inv_plan, dict) else "N/A"
    inv_complex  = inv_plan.get("investigation_complexity", "N/A") if isinstance(inv_plan, dict) else "N/A"
    req_docs     = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
    risk_tags    = case_input.get("risk_tags") or []
    tags_str     = ", ".join(risk_tags) if risk_tags else "None"
    ev_match     = case_input.get("evidence_match")
    wf_plan      = case_input.get("workflow_plan") or {}
    completed    = wf_plan.get("completed_agents", []) if isinstance(wf_plan, dict) else []

    _TOOL_ORDER = [
        "evaluate_evidence_completeness",
        "identify_missing_evidence",
        "validate_evidence_consistency",
        "assess_evidence_strength",
        "determine_next_document_request",
    ]

    tool_section = "\n\n## PRE-COMPUTED TOOL RESULTS\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    req_docs_str = "\n".join(f"  • {d}" for d in req_docs) if req_docs else "  • None defined"

    return (
        "## Case Context (read from database)\n"
        f"Case ID                   : {case_input.get('case_id', 'N/A')}\n"
        f"Dispute Category          : {case_input.get('dispute_category', 'N/A')}\n"
        f"Fraud Suspicion (AI)      : {case_input.get('fraud_suspicion', False)}\n"
        f"Amount                    : {case_input.get('currency', 'INR')} {case_input.get('amount', 0)}\n"
        f"Priority                  : {case_input.get('priority', 'N/A')}\n"
        f"Risk Tags                 : {tags_str}\n"
        f"Evidence Match (Agent 1)  : {ev_match}\n"
        f"Evidence Match Note       : {case_input.get('evidence_match_note', 'N/A')}\n"
        "\n## Agent 2 Investigation Summary\n"
        f"Recommended Queue         : {inv_queue}\n"
        f"Investigation Complexity  : {inv_complex}\n"
        f"Required Documents        :\n{req_docs_str}\n"
        "\n## Agent 3 Workflow Context\n"
        f"Completed Agents          : {completed or ['None']}\n"
        + tool_section
    )


def run_evidence_agent(case_id: str) -> dict:
    """
    Read case from DB, pre-run all 5 evidence tools, synthesise via LLM,
    return a complete evidence assessment.

    Always returns a valid dict — falls back gracefully if the graph fails.
    """
    from agents.evidence_agent.nodes.pipeline import _fallback_output
    from agents.evidence_agent.config import get_llm_config
    import uuid

    start_time = time.time()

    try:
        case_input = _read_case_from_db(case_id)
    except Exception as exc:
        agent_logger.error(f"EIA DB read failed for {case_id}: {exc}", exc_info=True)
        return {
            "case_id":                      case_id,
            "evidence_completeness":        0,
            "evidence_strength":            "LOW",
            "evidence_strength_score":      0.0,
            "evidence_consistent":          False,
            "consistency_issues":           ["Case not found in database"],
            "missing_documents":            [],
            "recommended_document_requests": [],
            "investigation_blocked":        True,
            "evidence_summary":             [f"EIA DB read failed: {exc}. Manual review required."],
            "review_recommendation":        "Manual review required — automated evidence assessment could not be completed.",
            "manual_evidence_review":       True,
            "tool_decisions":               [],
            "tools_used":                   [],
            "agent_metadata":               {},
            "metrics":                      {},
            "fallback_mode":                True,
            "failure_reason":               "DB_READ_FAILURE",
            "created_at":                   utc_now_iso(),
        }

    # Pre-run all 5 tools
    tool_results, tools_used = _run_tools(case_id)

    initial: EvidenceAgentState = {
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
        result = evidence_graph.invoke(initial, config={"recursion_limit": 4})
        return result["final_output"]
    except Exception as exc:
        agent_logger.error(f"EIA graph failed for {case_id}: {exc}", exc_info=True)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        cfg = get_llm_config()
        meta = {
            "agent_name":            "Evidence Intelligence Agent",
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
