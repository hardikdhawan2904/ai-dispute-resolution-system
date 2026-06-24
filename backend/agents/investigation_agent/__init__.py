"""
Agent 2 — IIA (Investigation Intelligence Agent)

Reads Agent 1's classification results directly from the database (dispute_cases),
not from an in-memory dict. This is the save-first architecture:
  Agent 1 saves → Agent 2 reads from DB → Agent 2 saves

DB reads:
  - dispute_cases       : Agent 1 classification results (case_id, category, tags, etc.)
  - dispute_history     : customer history, related cases
  - merchant_profiles   : merchant risk profile
  - transactions        : duplicate detection
  - dispute_cases       : live case history for customer/merchant/related queries
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.investigation_agent.graph import investigation_graph
from agents.investigation_agent.state import InvestigationAgentState
from agents.investigation_agent.tools import _active_case_id
from prompts.investigation_prompts import SYSTEM_PROMPT as _SYSTEM_PROMPT
from utils.pii_masking import mask_id, mask_free_text
from services.document_rules import get_required_documents

_MERCHANT_CATS = {"Merchant Dispute", "Refund Not Received", "Product Not Received", "Subscription Abuse"}


def _read_agent1_results_from_db(case_id: str) -> dict:
    """
    Read Agent 1's classification results from dispute_cases.
    Called at the start of Agent 2 so it works from the persisted state,
    not from the in-memory dict passed through the workflow.
    """
    from database.database import SessionLocal
    from database.models import DisputeCase
    from utils.logger import agent_logger

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found in database")

        agent_logger.info(f"Agent 2 reading Agent 1 results from DB for case {case_id}")
        return {
            "case_id":               case.case_id,
            "customer_id":           case.customer_id,
            "customer_name":         case.customer_name or "",
            "transaction_id":        case.transaction_id,
            "transaction_type":      case.transaction_type,
            "merchant":              case.merchant or "",
            "amount":                case.amount,
            "currency":              case.currency,
            "dispute_reason":        case.dispute_reason or "",
            "fraud_selected":        case.fraud_selected,
            # Agent 1 outputs — now read from DB, not in-memory
            "dispute_category":      case.dispute_category or "Other",
            "fraud_suspicion":       case.fraud_suspicion,
            "confidence_score":      case.confidence_score,
            "risk_tags":             case.risk_tags or [],
            "structured_reasoning":  case.structured_reasoning or "",
            "customer_intent_summary": case.customer_intent_summary or "",
            "evidence_match":        case.evidence_match,
        }
    finally:
        db.close()


def _run_tools_parallel(a1: dict, active_case_id: str) -> tuple:
    """Run all 4 IIA tools in parallel threads against the database."""
    from agents.investigation_agent.tools import (
        lookup_customer_history, check_merchant_risk,
        find_duplicate_transaction, lookup_related_cases,
    )
    cat      = a1.get("dispute_category", "Other")
    merchant = (a1.get("merchant") or "")[:50]

    task_defs = {
        "lookup_customer_history": (
            lookup_customer_history,
            {"customer_id": a1.get("customer_id", "")},
        ),
        "check_merchant_risk": (
            check_merchant_risk,
            {"merchant_name": merchant},
        ),
        "find_duplicate_transaction": (
            find_duplicate_transaction,
            {
                "transaction_id": a1.get("transaction_id", ""),
                "customer_id":    a1.get("customer_id", ""),
                "amount":         float(a1.get("amount", 0)),
                "merchant":       merchant[:30],
            },
        ),
        "lookup_related_cases": (
            lookup_related_cases,
            {
                "dispute_category": cat,
                "merchant": merchant if cat in _MERCHANT_CATS else "",
            },
        ),
    }

    def _run_one(name: str, tool_fn, args: dict) -> tuple:
        tok = _active_case_id.set(active_case_id)
        try:
            return name, tool_fn.invoke(args)
        except Exception as exc:
            return name, f"{name.upper()}\n  Error: Tool execution failed — {exc}"
        finally:
            _active_case_id.reset(tok)

    results: dict = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_run_one, name, fn, args): name
            for name, (fn, args) in task_defs.items()
        }
        for fut in as_completed(futures):
            name, result = fut.result()
            results[name] = result

    return results, list(results.keys())


def run_investigation_agent(agent1_output: dict) -> dict:
    """
    Entry point called by dispute_workflow after Agent 1 completes and saves to DB.

    Reads Agent 1 results fresh from dispute_cases (not from the passed dict)
    so Agent 2 always works from the persisted, authoritative DB state.
    Falls back to the passed dict if DB read fails.
    """
    active_case_id = agent1_output.get("case_id", "")

    # Read Agent 1 results from DB — primary path (save-first architecture)
    if active_case_id:
        try:
            a1 = _read_agent1_results_from_db(active_case_id)
        except Exception as exc:
            from utils.logger import agent_logger
            agent_logger.warning(
                f"Agent 2 DB read failed for {active_case_id}, using in-memory fallback: {exc}"
            )
            a1 = agent1_output
    else:
        a1 = agent1_output

    # Run all 4 DB-querying tools in parallel
    token = _active_case_id.set(active_case_id)
    try:
        pre_tool_results, pre_tools_used = _run_tools_parallel(a1, active_case_id)
    finally:
        _active_case_id.reset(token)

    token = _active_case_id.set(active_case_id)
    try:
        initial: InvestigationAgentState = {
            "messages": [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=_build_human_message(a1, pre_tool_results)),
            ],
            "agent1_output":          a1,
            "tool_results":           pre_tool_results,
            "investigation_findings": {},
            "final_output":           {},
            "error":                  None,
            "tools_used":             pre_tools_used,
            "agent_metadata":         {},
            "metrics":                {},
            "agent_start_time":       time.time(),
        }
        result = investigation_graph.invoke(initial, config={"recursion_limit": 4})
    finally:
        _active_case_id.reset(token)

    return result["final_output"]


def _build_human_message(a1: dict, tool_results: dict) -> str:
    risk_tags = a1.get("risk_tags") or []
    tags_str  = ", ".join(risk_tags) if risk_tags else "None"

    req_docs = get_required_documents(
        category         = a1.get("dispute_category", "Other"),
        fraud_selected   = a1.get("fraud_suspicion", False),
        amount           = float(a1.get("amount", 0)),
        transaction_type = a1.get("transaction_type", ""),
        risk_tags        = risk_tags,
    )
    docs_section = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(req_docs))

    _TOOL_ORDER = [
        "lookup_customer_history", "check_merchant_risk",
        "find_duplicate_transaction", "lookup_related_cases",
    ]
    tool_section = "\n\n## PRE-COMPUTED TOOL RESULTS\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    masked_intent = mask_free_text(a1.get("customer_intent_summary", "N/A"))

    return (
        "## Agent 1 Classification Output (read from database)\n"
        f"Case ID              : {mask_id(a1.get('case_id', 'N/A'))}\n"
        f"Customer ID          : {mask_id(a1.get('customer_id', 'N/A'))}\n"
        f"Transaction ID       : {mask_id(a1.get('transaction_id', 'N/A'), prefix_chars=8)}\n"
        f"Merchant             : {a1.get('merchant', 'N/A')}\n"
        f"Amount               : {a1.get('currency', 'INR')} {a1.get('amount', 0)}\n"
        f"Dispute Category     : {a1.get('dispute_category', 'N/A')}\n"
        f"Fraud Suspicion      : {a1.get('fraud_suspicion', False)}\n"
        f"Confidence Score     : {a1.get('confidence_score', 0.0)}\n"
        f"Risk Tags            : {tags_str}\n"
        f"Customer Intent      : {masked_intent}\n"
        f"\n## REQUIRED DOCUMENTS (pre-computed — copy exactly into required_documents field)\n"
        f"{docs_section}\n"
        + tool_section
    )

