"""
ReAct pipeline nodes.

call_model     : invoke LLM (with all 4 tools bound) against the current message history
should_continue: route to 'tools' if tool calls are pending, else to 'finalize'
finalize_node  : parse the LLM's final JSON and stamp server-side fields — nothing else
"""
from __future__ import annotations

import os
from typing import Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.dispute_agent.config import get_llm_config
from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import TOOLS
from utils.helpers import extract_json_from_text, utc_now_iso, generate_case_id
from utils.logger import agent_logger, log_workflow_event

# ── LLM (config sourced from agent.yaml) ─────────────────────────────────────
_cfg = get_llm_config()
_llm = ChatGroq(
    model_name=_cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=_cfg["max_tokens"],
    api_key=os.environ.get("GROQ_API_KEY"),
)
_llm_with_tools = _llm.bind_tools(TOOLS)


# ── Nodes ─────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def call_model(state: DisputeAgentState) -> dict:
    """Agent node — invoke LLM with the full message history."""
    response = _llm_with_tools.invoke(state["messages"])
    agent_logger.debug(
        "LLM response received",
        extra={"tool_calls": len(getattr(response, "tool_calls", None) or [])},
    )
    return {"messages": [response]}


def should_continue(state: DisputeAgentState) -> Literal["tools", "finalize"]:
    """Conditional edge — tool calls pending → tools node, otherwise → finalize."""
    last: AIMessage = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"


def finalize_node(state: DisputeAgentState) -> dict:
    """
    Parse the LLM's final JSON and stamp the server-owned fields.
    No tool calls here — the LLM called all tools autonomously before this.
    """
    d = state["dispute_input"]
    case_id = _extract_case_id(state["messages"]) or d.get("case_id") or generate_case_id()

    last = state["messages"][-1]
    raw = last.content if hasattr(last, "content") else ""
    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("LLM JSON parse failed — using fallback", extra={"case_id": case_id})
        amount = float(d.get("amount", 0))
        fraud = bool(d.get("fraud_selected", False))
        return {"final_case": _fallback_case(d, case_id, amount, fraud)}

    # Only fields the server owns — everything else came from the LLM via its tools
    parsed["case_id"]        = case_id
    parsed["customer_id"]    = d.get("customer_id", "")
    parsed["transaction_id"] = d.get("transaction_id", "")
    parsed.setdefault("status",         "Dispute Raised")
    parsed.setdefault("workflow_ready", True)
    parsed.setdefault("created_at",     utc_now_iso())

    log_workflow_event(
        agent_logger,
        event="AGENT_ANALYSIS_COMPLETE",
        stage="dispute_understanding",
        case_id=case_id,
        customer_id=d.get("customer_id"),
        extra={
            "dispute_category": parsed.get("dispute_category"),
            "priority":         parsed.get("priority"),
            "confidence_score": parsed.get("confidence_score"),
            "fraud_suspicion":  parsed.get("fraud_suspicion"),
        },
    )
    return {"final_case": parsed}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_case_id(messages: list) -> str:
    """Scan ToolMessages for the case_id returned by validate_dispute_input."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, str) and content.strip().startswith("CASE-"):
                return content.strip()
    return ""


def _fallback_priority(amount: float, fraud: bool) -> str:
    if fraud and amount > 50_000: return "CRITICAL"
    if fraud or amount > 50_000:  return "HIGH"
    if amount > 10_000:           return "MEDIUM"
    return "LOW"


def _fallback_case(d: dict, case_id: str, amount: float, fraud: bool) -> dict:
    return {
        "case_id":                 case_id,
        "customer_id":             d.get("customer_id", ""),
        "transaction_id":          d.get("transaction_id", ""),
        "transaction_type":        d.get("transaction_type", ""),
        "merchant":                d.get("merchant", ""),
        "amount":                  amount,
        "currency":                d.get("currency", "INR"),
        "dispute_category":        "Other",
        "fraud_suspicion":         fraud,
        "customer_intent_summary": (
            "Automated analysis failed — manual review required. "
            f"Customer reported: {d.get('dispute_reason', 'N/A')}"
        ),
        "priority":             _fallback_priority(amount, fraud),
        "confidence_score":     0.1,
        "risk_tags":            ["HIGH_PRIORITY_CASE"] if fraud else [],
        "structured_reasoning": "AI analysis could not be completed. Manual investigation required.",
        "evidence_match":       None,
        "evidence_match_note":  "",
        "status":               "Dispute Raised",
        "workflow_ready":       True,
        "created_at":           utc_now_iso(),
    }
