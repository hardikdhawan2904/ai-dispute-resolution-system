"""
Agent 1 — ARIA (Dispute Understanding Agent)

Job: Read the customer's submission from the database, use 3 analytical tools
     to gather structured intelligence, then classify the dispute and score
     confidence. Nothing more — investigation is Agent 2's responsibility.

DB interaction:
  - Reads case data from dispute_cases by case_id (save-first architecture)
  - score_fraud_indicators also queries account_events, customer_devices (DB-first)
  - Document texts passed in-memory (already extracted before this call)

Tools (pre-computed server-side before LLM call):
  assess_transaction_context  → amount tier, time-of-day, card-not-present signals
  score_fraud_indicators      → DB-first fraud signal scorer (account_events primary)
  verify_evidence_match       → document corroboration check (called if docs attached)
  Note: compute_confidence_score removed — confidence computed deterministically in finalize_node
"""
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from agents.dispute_agent.graph import dispute_graph
from agents.dispute_agent.state import DisputeAgentState
from services.dispute_understanding_fallback_service import (
    classify_failure,
    generate_agent1_fallback,
)
from utils.logger import agent_logger


def _read_case_from_db(case_id: str) -> dict:
    """Read case data from dispute_cases table by case_id."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found in database")
        return {
            "case_id":              case.case_id,
            "customer_id":          case.customer_id,
            "customer_name":        case.customer_name or "",
            "email":                case.email or "",
            "phone":                case.phone or "",
            "transaction_id":       case.transaction_id,
            "transaction_type":     case.transaction_type,
            "merchant":             case.merchant or "",
            "amount":               case.amount,
            "currency":             case.currency,
            "transaction_date":     case.transaction_date or "",
            "transaction_time":     case.transaction_time or "",
            "customer_comment":     case.customer_comment or "",
            "dispute_reason":       case.dispute_reason or "",
            "fraud_selected":       case.fraud_selected,
            "transaction_metadata": case.transaction_metadata or {},
        }
    finally:
        db.close()


def run_dispute_agent(
    dispute_input: dict,
    document_texts: Optional[List[str]] = None,
    case_id: Optional[str] = None,
) -> dict:
    """
    Read case from DB, understand the dispute, return a fully structured case dict.

    If case_id is provided, reads fresh data from dispute_cases table (save-first).
    Falls back to dispute_input dict if case_id is not provided (backward compat).
    Always returns a valid dict — falls back gracefully if the graph fails.
    """
    # Read from DB if case_id provided — this is the primary path
    if case_id:
        try:
            dispute_input = _read_case_from_db(case_id)
            agent_logger.info(f"Agent 1 reading case {case_id} from database")
        except Exception as exc:
            agent_logger.warning(f"Agent 1 DB read failed for {case_id}, using in-memory input: {exc}")
            # Fall through to use the passed dispute_input

    initial: DisputeAgentState = {
        "messages":            [],
        "dispute_input":       dispute_input,
        "document_texts":      document_texts or [],
        "case_id":             dispute_input.get("case_id", ""),
        "supporting_evidence": "",
        "document_section":    "",
        "final_case":          {},
        "error":               None,
        "tools_used":          [],
        "agent_metadata":      {},
        "metrics":             {},
        "agent_start_time":    0.0,
    }
    try:
        result = dispute_graph.invoke(initial, config={"recursion_limit": 12})
        return result["final_case"]
    except Exception as exc:
        failure_reason = classify_failure(exc)
        agent_logger.error(
            f"Agent 1 graph failed ({failure_reason}): {exc}",
            exc_info=True,
        )
        return generate_agent1_fallback(dispute_input, failure_reason)

