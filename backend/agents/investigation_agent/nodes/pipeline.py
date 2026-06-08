"""
Investigation Intelligence Agent — ReAct pipeline nodes.

call_model      : invoke LLM with all 5 tools bound (via TOOL_REGISTRY + agent.yaml)
should_continue : route to 'tools' if tool calls pending, else to 'finalize'
finalize_node   : parse the LLM's final JSON, extract tool_results from message history,
                  stamp server-owned audit fields (tools_used, agent_metadata, metrics),
                  assemble final_output
"""
from __future__ import annotations

import os
import time
from typing import Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from groq import RateLimitError as GroqRateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.investigation_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.investigation_agent.state import InvestigationAgentState
from agents.investigation_agent.tools import TOOL_REGISTRY
from services.investigation_confidence_service import (
    calculate_investigation_confidence,
    generate_confidence_factors,
)
from utils.helpers import extract_json_from_text, utc_now_iso
from utils.logger import agent_logger, log_workflow_event

# ── LLM + tools + agent identity (all sourced from agent.yaml) ───────────────
_cfg        = get_llm_config()
_agent_yaml = load_agent_config()["agent"]
_AGENT_NAME = _agent_yaml["full_name"]       # "Investigation Intelligence Agent"
_AGENT_VER  = str(_agent_yaml["version"])    # "1.2.0"
_tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

_llm = ChatGroq(
    model_name=os.environ.get("LLM_MODEL") or _cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=_cfg["max_tokens"],
    api_key=os.environ.get("GROQ_API_KEY"),
)
_llm_with_tools = _llm.bind_tools(_tools, parallel_tool_calls=True)


# ── Nodes ──────────────────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_not_exception_type(GroqRateLimitError),
    reraise=True,
)
def call_model(state: InvestigationAgentState) -> dict:
    """Agent node — tools are pre-computed; single LLM call synthesises and produces JSON."""
    response = _llm.invoke(state["messages"])
    agent_logger.debug("IIA LLM response received", extra={"tool_calls": 0})
    return {"messages": [response]}


def should_continue(state: InvestigationAgentState) -> Literal["tools", "finalize"]:
    """Conditional edge — tool calls pending → tools node, otherwise → finalize."""
    last: AIMessage = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"


def finalize_node(state: InvestigationAgentState) -> dict:
    """
    Parse the LLM's final JSON investigation plan.
    Extracts audit trail from message history.
    Stamps server-owned fields: tools_used, agent_metadata, metrics.
    Assembles final_output.
    """
    a1      = state["agent1_output"]
    case_id = a1.get("case_id", "")

    # ── Timing ────────────────────────────────────────────────────────────────
    start_time  = state.get("agent_start_time") or 0.0
    duration_ms = round((time.time() - start_time) * 1000, 1) if start_time else 0.0

    # ── Audit trail — merge pre-computed tools from state + any ReAct messages ──
    messages       = state.get("messages") or []
    # Pre-computed tools passed in via state (populated before graph invocation)
    tool_results:  dict = dict(state.get("tool_results") or {})
    tools_used:    list = list(state.get("tools_used") or [])
    llm_call_count = 0
    tool_msg_count = len(tool_results)

    for msg in messages:
        if isinstance(msg, AIMessage):
            llm_call_count += 1
            for tc in (getattr(msg, "tool_calls", None) or []):
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name and name not in tools_used:
                    tools_used.append(name)
        elif isinstance(msg, ToolMessage):
            tool_msg_count += 1
            if getattr(msg, "name", None):
                tool_results[msg.name] = msg.content

    metrics = {
        "total_duration_ms": duration_ms,
        "llm_calls":         llm_call_count,
        "tool_calls":        tool_msg_count,
        "retry_count":       0,
    }
    agent_metadata = {
        "agent_name":           _AGENT_NAME,
        "agent_version":        _AGENT_VER,
        "model":                _cfg["model"],
        "execution_timestamp":  utc_now_iso(),
        "execution_duration_ms": duration_ms,
    }

    # ── Parse LLM final JSON ──────────────────────────────────────────────────
    last   = messages[-1] if messages else None
    raw    = last.content if last and hasattr(last, "content") else ""
    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("IIA JSON parse failed — using fallback", extra={"case_id": case_id})
        fb = _fallback_output(a1, case_id, tools_used, agent_metadata, metrics)
        return {
            "final_output":   fb,
            "tool_results":   tool_results,
            "tools_used":     tools_used,
            "agent_metadata": agent_metadata,
            "metrics":        metrics,
        }

    # ── Stamp server-owned fields ─────────────────────────────────────────────
    parsed["case_id"]    = case_id
    parsed["created_at"] = utc_now_iso()

    # Server-stamped audit fields — LLM cannot fabricate these
    parsed["tools_used"]     = tools_used
    parsed["agent_metadata"] = agent_metadata
    parsed["metrics"]        = metrics

    # Ensure LLM-generated fields default gracefully if LLM omits them
    parsed.setdefault("investigation_reasoning",  [])
    parsed.setdefault("queue_confidence",         0.7)
    parsed.setdefault("queue_confidence_factors", [])
    parsed.setdefault("tool_decisions",           [])
    parsed.setdefault("investigation_gaps",        [])
    parsed.setdefault("data_quality_score",        0.7)
    parsed.setdefault("data_quality_factors",      [])
    parsed.setdefault("manual_review_reason",      [])

    # Server-stamp required_documents — deterministic, never trust LLM output for this
    from services.document_rules import get_required_documents
    parsed["required_documents"] = get_required_documents(
        category       = a1.get("dispute_category", "Other"),
        fraud_selected = a1.get("fraud_suspicion", False),
        amount         = float(a1.get("amount", 0)),
        risk_tags      = a1.get("risk_tags") or [],
    )

    # Server-stamp investigation_coverage — derived from actual tool execution records
    parsed["investigation_coverage"] = {
        "customer_history_checked":  "lookup_customer_history" in tools_used,
        "merchant_history_checked":  "check_merchant_risk" in tools_used,
        "duplicate_check_performed": "find_duplicate_transaction" in tools_used,
        "related_cases_reviewed":    "lookup_related_cases" in tools_used,
    }

    # Merge Agent 1 classification fields into plan dict for confidence calculation
    # (fraud_suspicion, dispute_category, risk_tags come from a1, not the LLM output)
    confidence_input = {
        **parsed,
        "fraud_suspicion":  a1.get("fraud_suspicion", False),
        "dispute_category": a1.get("dispute_category", "Other"),
        "risk_tags":        a1.get("risk_tags") or [],
    }

    # Server-stamp investigation confidence (deterministic, not LLM-generated)
    parsed["investigation_confidence"]         = calculate_investigation_confidence(confidence_input)
    parsed["investigation_confidence_factors"] = generate_confidence_factors(confidence_input)

    log_workflow_event(
        agent_logger,
        event="IIA_INVESTIGATION_COMPLETE",
        stage="investigation_intelligence",
        case_id=case_id,
        customer_id=a1.get("customer_id"),
        extra={
            "recommended_queue":        parsed.get("recommended_queue"),
            "queue_confidence":         parsed.get("queue_confidence"),
            "investigation_complexity": parsed.get("investigation_complexity"),
            "manual_review_required":   parsed.get("manual_review_required"),
            "duplicate_found":          parsed.get("duplicate_found"),
            "confidence_score":         parsed.get("confidence_score"),
            "tools_used":               tools_used,
            "duration_ms":              duration_ms,
        },
    )

    return {
        "final_output":   parsed,
        "tool_results":   tool_results,
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
    }


# ── Fallback ───────────────────────────────────────────────────────────────────

def _fallback_output(
    a1: dict, case_id: str,
    tools_used: list, agent_metadata: dict, metrics: dict,
) -> dict:
    """Minimal safe investigation plan returned when JSON parsing fails."""
    fraud   = a1.get("fraud_suspicion", False)
    amount  = float(a1.get("amount", 0))
    cat     = a1.get("dispute_category", "Other")

    if fraud and amount > 50_000:
        queue      = "CRITICAL_QUEUE"
        complexity = "CRITICAL"
        q_conf     = 0.75
    elif fraud:
        queue      = "FRAUD_QUEUE"
        complexity = "HIGH"
        q_conf     = 0.70
    elif amount > 50_000:
        queue      = "HIGH_VALUE_QUEUE"
        complexity = "HIGH"
        q_conf     = 0.70
    elif cat in ("Merchant Dispute", "Refund Not Received", "Product Not Received", "Subscription Abuse"):
        queue      = "MERCHANT_QUEUE"
        complexity = "MEDIUM"
        q_conf     = 0.65
    elif cat == "ATM Cash Issue":
        queue      = "ATM_QUEUE"
        complexity = "MEDIUM"
        q_conf     = 0.65
    else:
        queue      = "STANDARD_QUEUE"
        complexity = "MEDIUM"
        q_conf     = 0.50

    from services.document_rules import get_required_documents
    fallback_docs = get_required_documents(
        category       = cat,
        fraud_selected = fraud,
        amount         = amount,
    )

    investigation_coverage = {
        "customer_history_checked":  "lookup_customer_history" in tools_used,
        "merchant_history_checked":  "check_merchant_risk" in tools_used,
        "duplicate_check_performed": "find_duplicate_transaction" in tools_used,
        "related_cases_reviewed":    "lookup_related_cases" in tools_used,
    }

    return {
        "case_id":                  case_id,
        "recommended_queue":        queue,
        "queue_confidence":         q_conf,
        "queue_confidence_factors": [
            "Queue assigned using deterministic fallback rules — automated investigation failed.",
            "Confidence is reduced because tool-based intelligence could not be gathered.",
        ],
        "investigation_complexity": complexity,
        "manual_review_required":   True,
        "manual_review_reason": [
            "Automated investigation failed — LLM output could not be parsed.",
            f"Fallback routing applied for category '{cat}' — human analyst must verify.",
        ],
        "customer_risk_profile":    {"risk_level": "UNKNOWN", "assessment": "Tool execution failed — manual assessment required."},
        "merchant_risk_profile":    {"merchant_risk": "UNKNOWN", "assessment": "Tool execution failed — manual assessment required."},
        "duplicate_found":          False,
        "related_case_id":          None,
        "related_cases":            {"similar_cases": 0, "resolution_rate": 0.0},
        "required_documents":       fallback_docs,
        "recommended_steps": [
            "Manual review required — automated investigation failed.",
            "Gather all available evidence from customer.",
            "Escalate to senior analyst.",
        ],
        "investigation_reasoning": [
            "Automated investigation could not complete — LLM output was not parseable.",
            f"Fallback queue assignment applied based on dispute category ({cat}) and fraud flag ({fraud}).",
        ],
        "investigation_summary": (
            "Automated investigation could not be completed. "
            "Manual review has been flagged. Senior analyst should conduct full investigation."
        ),
        "tool_decisions":       [],
        "investigation_gaps":   [
            "Automated investigation failed — all tool-based intelligence is unavailable.",
        ],
        "data_quality_score":   0.1,
        "data_quality_factors": [
            "LLM output parsing failed — investigation data quality cannot be assessed.",
            f"Fallback routing applied — no tool intelligence was synthesised.",
        ],
        "investigation_coverage": investigation_coverage,
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
        "confidence_score":                0.1,
        "investigation_confidence":        0.10,
        "investigation_confidence_factors": ["Automated investigation failed — confidence cannot be computed."],
        "created_at":     utc_now_iso(),
    }
