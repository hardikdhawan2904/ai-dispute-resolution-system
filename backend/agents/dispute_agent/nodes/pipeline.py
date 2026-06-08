"""
Agent 1 (ARIA) — ReAct pipeline nodes.

validate_node       : extract case_id from submission
build_evidence_node : format fraud-indicator checklist + document text,
                      then build the initial [SystemMessage, HumanMessage] to start the loop
call_model          : agent node — invoke LLM with 4 understanding tools bound
should_continue     : route to 'tools' if tool calls pending, else to 'finalize'
finalize_node       : parse the LLM's final JSON, stamp server-owned fields, return final_case
"""
from __future__ import annotations

import os
import time
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from groq import RateLimitError as GroqRateLimitError
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.dispute_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import TOOL_REGISTRY
from prompts.dispute_prompts import SYSTEM_PROMPT, DISPUTE_DATA_TEMPLATE
from utils.helpers import extract_json_from_text, utc_now_iso, generate_case_id
from utils.logger import agent_logger, log_workflow_event
from utils.pii_masking import mask_name, mask_id, mask_document, mask_free_text

# ── LLM + tools + agent identity (all sourced from agent.yaml) ───────────────
_cfg        = get_llm_config()
_agent_yaml = load_agent_config()["agent"]
_AGENT_NAME = _agent_yaml["name"]      # "ARIA"
_AGENT_VER  = str(_agent_yaml["version"])  # "1.0"
_tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

_llm = ChatGroq(
    model_name=os.environ.get("LLM_MODEL") or _cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=int(os.environ.get("LLM_MAX_TOKENS") or _cfg["max_tokens"]),
    api_key=os.environ.get("GROQ_API_KEY"),
)
_llm_with_tools = _llm.bind_tools(_tools)  # kept for graph wiring; call_model uses plain _llm


# ── Node 1 — validate ─────────────────────────────────────────────────────────

def validate_node(state: DisputeAgentState) -> dict:
    d = state["dispute_input"]
    case_id = d.get("case_id") or d.get("_preset_case_id") or generate_case_id()
    return {"case_id": case_id, "agent_start_time": time.time()}


# ── Node 2 — build_evidence ───────────────────────────────────────────────────

def build_evidence_node(state: DisputeAgentState) -> dict:
    """Format fraud checklist + document section, then build initial messages."""
    meta = state["dispute_input"].get("transaction_metadata") or {}
    d    = state["dispute_input"]

    def yn(val) -> str:
        if val is True:  return "Yes"
        if val is False: return "No"
        return str(val) if val else "Not provided"

    supporting_evidence = (
        f"  OTP Received (for this txn)  : {yn(meta.get('otp_received'))}\n"
        f"  Card / Account Blocked       : {yn(meta.get('card_blocked'))}\n"
        f"  Bank Already Contacted       : {yn(meta.get('bank_contacted'))}\n"
        f"  Transaction Location         : {meta.get('transaction_location') or 'Not provided'}\n"
        f"  OTP Shared with 3rd Party    : {yn(meta.get('otp_shared'))}\n"
        f"  Bank Impersonation Call      : {yn(meta.get('bank_impersonation'))}\n"
        f"  Remote Access App Installed  : {yn(meta.get('remote_access'))}\n"
        f"  Phishing Link Clicked        : {yn(meta.get('phishing_link'))}\n"
        f"  SIM Swap Suspected           : {yn(meta.get('sim_swap_suspected'))}\n"
        f"  Device Lost / Stolen         : {yn(meta.get('device_lost'))}\n"
        f"  Card Lost / Stolen           : {yn(meta.get('card_lost'))}\n"
        f"  Unknown Beneficiary Added    : {yn(meta.get('unknown_beneficiary'))}\n"
        f"  UPI Collect Fraud            : {yn(meta.get('upi_collect_fraud'))}\n"
        f"  Steps Already Taken          : {meta.get('fraud_additional_details') or 'None stated'}\n"
    )

    doc_texts = state.get("document_texts") or []
    if doc_texts:
        parts = [t[:3000] + ("..." if len(t) > 3000 else "") for t in doc_texts if t.strip()]
        document_section = "\n\n".join(parts) if parts else "No documents attached."
    else:
        document_section = "No documents attached."

    # ── Mask PII from free-text fields before anything reaches the LLM ─────────
    masked_comment = mask_free_text(d.get("customer_comment", ""))

    # ── Pre-compute all tools server-side (eliminates ReAct LLM round-trips) ─
    from agents.dispute_agent.tools import (
        assess_transaction_context, score_fraud_indicators, verify_evidence_match,
    )
    txn_risk = assess_transaction_context.invoke({
        "amount":            float(d.get("amount", 0)),
        "transaction_type":  d.get("transaction_type", ""),
        "merchant":          d.get("merchant", ""),
        "transaction_date":  d.get("transaction_date", ""),
        "transaction_time":  d.get("transaction_time", ""),
    })
    fraud_score = score_fraud_indicators.invoke({
        "customer_comment":   masked_comment,
        "otp_received":       yn(meta.get("otp_received")),
        "otp_shared":         yn(meta.get("otp_shared")),
        "bank_impersonation": yn(meta.get("bank_impersonation")),
        "remote_access":      yn(meta.get("remote_access")),
        "phishing_link":      yn(meta.get("phishing_link")),
        "sim_swap_suspected": yn(meta.get("sim_swap_suspected")),
        "card_lost":          yn(meta.get("card_lost")),
        "device_lost":        yn(meta.get("device_lost")),
        "bank_contacted":     yn(meta.get("bank_contacted")),
        "card_blocked":       yn(meta.get("card_blocked")),
    })
    if document_section != "No documents attached.":
        evidence_result = verify_evidence_match.invoke({
            "document_text":      document_section[:3000],
            "claimed_amount":     str(d.get("amount", "")),
            "claimed_merchant":   d.get("merchant", ""),
            "dispute_description": masked_comment[:500],
        })
    else:
        evidence_result = "EVIDENCE VERIFICATION\n  Verdict              : NO_DOCUMENTS\n  Evidence Match       : null\n  Note                 : No documents were submitted with this dispute."

    tool_results_section = (
        "\n\n## PRE-COMPUTED TOOL RESULTS\n\n"
        f"### assess_transaction_context\n{txn_risk}\n\n"
        f"### score_fraud_indicators\n{fraud_score}\n\n"
        f"### verify_evidence_match\n{evidence_result}\n"
    )

    masked_document_section = mask_document(document_section)

    # Build initial messages — LLM receives all tool outputs, produces JSON in one call
    human_content = DISPUTE_DATA_TEMPLATE.format(
        customer_name    = mask_name(d.get("customer_name", "N/A")),
        customer_id      = mask_id(d.get("customer_id", "N/A")),
        transaction_type = d.get("transaction_type", "N/A"),
        merchant         = d.get("merchant", "N/A"),
        amount           = d.get("amount", 0),
        currency         = d.get("currency", "INR"),
        transaction_date = d.get("transaction_date", "N/A"),
        transaction_time = d.get("transaction_time", "N/A"),
        dispute_reason   = d.get("dispute_reason", "N/A"),
        fraud_selected   = d.get("fraud_selected", False),
        customer_comment = masked_comment,
        supporting_evidence = supporting_evidence,
        document_section = masked_document_section,
        case_id          = mask_id(state["case_id"]),
        created_at       = utc_now_iso(),
    ) + tool_results_section

    return {
        "supporting_evidence": supporting_evidence,
        "document_section":    document_section,
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ],
    }


# ── Node 3 — agent (ReAct loop) ───────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=5),
    retry=retry_if_not_exception_type(GroqRateLimitError),
    reraise=True,
)
def call_model(state: DisputeAgentState) -> dict:
    """Agent node — tools are pre-computed; single LLM call produces final JSON."""
    response = _llm.invoke(state["messages"])
    agent_logger.debug("ARIA LLM response received", extra={"tool_calls": 0})
    return {"messages": [response]}


def should_continue(state: DisputeAgentState) -> Literal["tools", "finalize"]:
    """Conditional edge — tool calls pending → tools node, otherwise → finalize."""
    last: AIMessage = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"


# ── Node 4 — finalize ─────────────────────────────────────────────────────────

def finalize_node(state: DisputeAgentState) -> dict:
    """Parse the LLM's final JSON, stamp server-owned fields, assemble final_case."""
    case_id = state["case_id"]
    d       = state["dispute_input"]

    # ── Timing ───────────────────────────────────────────────────────────────
    start_time  = state.get("agent_start_time") or 0.0
    duration_ms = round((time.time() - start_time) * 1000, 1) if start_time else 0.0

    # ── Audit trail from message history ─────────────────────────────────────
    messages       = state.get("messages") or []
    tools_used:    list = []
    llm_call_count = 0
    tool_msg_count = 0

    for msg in messages:
        if isinstance(msg, AIMessage):
            llm_call_count += 1
            for tc in (getattr(msg, "tool_calls", None) or []):
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name and name not in tools_used:
                    tools_used.append(name)
        elif isinstance(msg, ToolMessage):
            tool_msg_count += 1

    metrics = {
        "total_duration_ms": duration_ms,
        "llm_calls":         llm_call_count,
        "tool_calls":        tool_msg_count,
        "retry_count":       0,
    }
    agent_metadata = {
        "name":        _AGENT_NAME,
        "version":     _AGENT_VER,
        "model":       _cfg["model"],
        "timestamp":   utc_now_iso(),
        "duration_ms": duration_ms,
    }

    # ── Parse LLM output ─────────────────────────────────────────────────────
    last = messages[-1] if messages else None
    raw  = last.content if last and hasattr(last, "content") else ""
    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("ARIA JSON parse failed — using fallback", extra={"case_id": case_id})
        amount = float(d.get("amount", 0))
        fraud  = bool(d.get("fraud_selected", False))
        # Stamp JSON_PARSE_ERROR into metrics before passing to _fallback_case
        metrics["fallback_activated"] = True
        metrics["failure_reason"]     = "JSON_PARSE_ERROR"
        metrics["fallback_timestamp"] = utc_now_iso()
        fc = _fallback_case(d, case_id, amount, fraud, tools_used, agent_metadata, metrics)
        return {"final_case": fc, "tools_used": tools_used, "agent_metadata": agent_metadata, "metrics": metrics}

    # ── Stamp server-owned and audit fields ───────────────────────────────────
    parsed["case_id"]        = case_id
    parsed["customer_id"]    = d.get("customer_id", "")
    parsed["transaction_id"] = d.get("transaction_id", "")
    parsed.setdefault("status",             "Dispute Raised")
    parsed.setdefault("workflow_ready",     True)
    parsed.setdefault("created_at",         utc_now_iso())
    parsed.setdefault("confidence_factors", [])
    # Normal execution — no fallback
    parsed.setdefault("fallback_mode",  False)
    parsed.setdefault("failure_reason", None)
    parsed["tools_used"]     = tools_used
    parsed["agent_metadata"] = agent_metadata
    # Stamp fallback_activated=False into metrics for normal runs
    metrics["fallback_activated"] = False
    parsed["metrics"]        = metrics

    log_workflow_event(
        agent_logger,
        event="AGENT_ANALYSIS_COMPLETE",
        stage="dispute_understanding",
        case_id=case_id,
        customer_id=d.get("customer_id"),
        extra={
            "dispute_category": parsed.get("dispute_category"),
            "confidence_score": parsed.get("confidence_score"),
            "fraud_suspicion":  parsed.get("fraud_suspicion"),
            "evidence_match":   parsed.get("evidence_match"),
            "tools_used":       tools_used,
            "duration_ms":      duration_ms,
        },
    )
    return {
        "final_case":     parsed,
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
    }


# ── Fallback ───────────────────────────────────────────────────────────────────

def _fallback_case(
    d: dict, case_id: str, amount: float, fraud: bool,
    tools_used: list, agent_metadata: dict, metrics: dict,
) -> dict:
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
        "confidence_score":        0.1,
        "confidence_factors":      [],
        "risk_tags":               ["HIGH_PRIORITY_CASE"] if fraud else [],
        "structured_reasoning":    "AI analysis could not be completed. Manual investigation required.",
        "evidence_match":          None,
        "evidence_match_note":     "",
        "status":         "Dispute Raised",
        "workflow_ready": True,
        "created_at":     utc_now_iso(),
        # JSON-parse-error fallback flags
        "fallback_mode":  True,
        "failure_reason": "JSON_PARSE_ERROR",
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
    }
