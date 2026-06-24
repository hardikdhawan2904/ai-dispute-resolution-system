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
import re
import time
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from groq import RateLimitError as GroqRateLimitError
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.dispute_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import TOOL_REGISTRY, _INTL_SIGNALS
from prompts.dispute_prompts import SYSTEM_PROMPT, DISPUTE_DATA_TEMPLATE
from utils.helpers import extract_json_from_text, utc_now_iso, generate_case_id
from utils.logger import agent_logger, log_workflow_event
from utils.pii_masking import mask_name, mask_id, mask_document, mask_free_text

_REQUIRED_FIELDS   = ("customer_id", "transaction_id", "dispute_reason",
                      "customer_comment", "merchant", "amount", "transaction_date")
_FRAUD_CATEGORIES  = frozenset({"Unauthorized Transaction", "Friendly Fraud"})

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
        "customer_id":        d.get("customer_id", ""),
        "transaction_id":     d.get("transaction_id", ""),
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

    # Tool pre-computation already analyzed all documents via verify_evidence_match.
    # Passing raw doc text to the LLM is redundant and causes token overflow on
    # Groq's on-demand tier (6000 TPM). Show only a compact summary instead.
    if doc_texts:
        _filenames = []
        for t in doc_texts:
            first_line = t.split("\n", 1)[0].strip()
            _filenames.append(first_line[1:-1] if first_line.startswith("[") else "document")
        masked_document_section = (
            f"{len(_filenames)} document(s) attached: "
            + ", ".join(_filenames)
            + "\n(Full text analyzed by verify_evidence_match — see PRE-COMPUTED TOOL RESULTS below.)"
        )
    else:
        masked_document_section = "No documents attached."

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

    # ── Parse pre-computed tool outputs from HumanMessage ────────────────────
    _evidence_verdict   = "NO_DOCUMENTS"
    _fraud_signal_level = "NONE"
    for msg in messages:
        if isinstance(msg, HumanMessage):
            for line in msg.content.splitlines():
                s = line.strip()
                if not s:
                    continue
                # verify_evidence_match: "Verdict              : MATCH"
                if s.startswith("Verdict") and ":" in s:
                    val = s.split(":", 1)[1].strip()
                    if val in ("MATCH", "PARTIAL_MATCH", "MISMATCH",
                               "NO_DOCUMENTS", "CANNOT_VERIFY"):
                        _evidence_verdict = val
                # score_fraud_indicators: "Fraud Signal Level   : HIGH (score: …)"
                if s.startswith("Fraud Signal Level") and ":" in s:
                    val = s.split(":", 1)[1].strip().split()[0]
                    if val in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"):
                        _fraud_signal_level = val
            break  # HumanMessage is the first non-system message

    # ── Server-stamp evidence provenance (evaluated_files / trace / summary) ──
    # Stored inside agent_metadata — no DB migration required.
    _verdict_confidence = {
        "MATCH": 0.92, "PARTIAL_MATCH": 0.75,
        "MISMATCH": 0.35, "CANNOT_VERIFY": 0.50, "NO_DOCUMENTS": 0.0,
    }
    _file_confidence = _verdict_confidence.get(_evidence_verdict, 0.50)

    def _infer_doc_type(fn: str) -> str:
        f = fn.lower()
        if ("bank" in f and "statement" in f) or "statement" in f: return "BANK_STATEMENT"
        if "fir" in f or "police" in f or "complaint_report" in f: return "POLICE_FIR"
        if "otp" in f:                                              return "OTP_RECORD"
        if "sms" in f or "alert" in f or "debit_alert" in f:       return "TRANSACTION_ALERT"
        if "complaint" in f:                                        return "COMPLAINT_LETTER"
        if "kyc" in f or "aadhaar" in f or "aadhar" in f or "passport" in f or "pan" in f: return "IDENTITY_DOCUMENT"
        if "source_of_funds" in f or "fund" in f or "salary" in f: return "FINANCIAL_DECLARATION"
        if "refund" in f or "email" in f or "mail" in f:           return "MERCHANT_COMMUNICATION"
        if "receipt" in f:                                          return "PAYMENT_RECEIPT"
        if "invoice" in f:                                          return "INVOICE"
        if "screenshot" in f or "screen" in f:                     return "TRANSACTION_SCREENSHOT"
        if "id" in f:                                               return "IDENTITY_DOCUMENT"
        if "photo" in f or "img" in f or "image" in f:             return "PHOTO_EVIDENCE"
        if "upi" in f:                                              return "UPI_RECORD"
        return "SUPPORTING_DOCUMENT"

    _doc_texts = state.get("document_texts") or []
    _evaluated_files = []
    for _block in _doc_texts:
        if not _block.strip():
            continue
        _first = _block.split("\n", 1)[0].strip()
        _fname = _first[1:-1] if (_first.startswith("[") and _first.endswith("]")) else "document"
        _evaluated_files.append({
            "filename":       _fname,
            "document_type":  _infer_doc_type(_fname),
            "used_by_agent1": True,
            "confidence":     _file_confidence,
        })

    _ev_note = str(parsed.get("evidence_match_note") or "").strip()
    if _ev_note:
        _evidence_source_summary = [_ev_note]
    elif _evidence_verdict == "MATCH":
        _evidence_source_summary = [f"{len(_evaluated_files)} submitted file(s) support the claimed dispute."]
    elif _evidence_verdict == "PARTIAL_MATCH":
        _evidence_source_summary = ["Submitted documents partially support the claim — additional verification may be required."]
    elif _evidence_verdict == "MISMATCH":
        _evidence_source_summary = ["Submitted documents DO NOT support the claim — transaction details conflict with the dispute."]
    else:
        _evidence_source_summary = ["No documents were submitted — evidence match not assessed."]

    agent_metadata["evaluated_files"]         = _evaluated_files
    agent_metadata["evidence_trace"]          = {
        "evidence_match":  parsed.get("evidence_match"),
        "verdict":         _evidence_verdict,
        "source_files":    [f["filename"] for f in _evaluated_files],
    }
    agent_metadata["evidence_source_summary"] = _evidence_source_summary
    parsed["agent_metadata"] = agent_metadata

    # ── Server-side confidence score (aligned with Tool 4 formula) ───────────
    comment    = str(d.get("customer_comment") or "")
    comment_lc = comment.lower()
    fraud_flag = bool(parsed.get("fraud_suspicion"))
    category   = str(parsed.get("dispute_category") or "")

    conf = 0.30   # reduced baseline — better discrimination between strong and exceptional cases

    # Data completeness (±0.10)
    if all(d.get(f) for f in _REQUIRED_FIELDS):
        conf += 0.10
    else:
        conf -= 0.10

    # Comment quality (±0.10)
    if len(comment) >= 80:
        conf += 0.10
    elif len(comment) < 30:
        conf -= 0.10

    # Evidence verdict — highest impact (±0.25)
    if _evidence_verdict == "MATCH":
        conf += 0.25
    elif _evidence_verdict == "PARTIAL_MATCH":
        conf += 0.10
    elif _evidence_verdict == "MISMATCH":
        conf -= 0.25
    # NO_DOCUMENTS, CANNOT_VERIFY: +0.00

    # Fraud signal alignment (±0.15 / +0.08 / -0.12)
    if fraud_flag and category in _FRAUD_CATEGORIES:
        if _fraud_signal_level in ("CRITICAL", "HIGH"):
            conf += 0.15
        elif _fraud_signal_level == "MEDIUM":
            conf += 0.08
    elif fraud_flag and category not in _FRAUD_CATEGORIES:
        if _fraud_signal_level in ("CRITICAL", "HIGH"):
            conf -= 0.12  # high fraud signals inconsistent with stated category

    parsed["confidence_score"] = round(max(0.10, min(1.00, conf)), 2)

    # Server-stamp confidence_factors — mirrors the formula above so display is always accurate
    _cf = []
    if all(d.get(f) for f in _REQUIRED_FIELDS):
        _cf.append("+0.10 all required fields present")
    else:
        _cf.append("-0.10 one or more required fields missing")
    if len(comment) >= 80:
        _cf.append("+0.10 comment is detailed")
    elif len(comment) < 30:
        _cf.append("-0.10 comment too brief")
    if _evidence_verdict == "MATCH":
        _cf.append("+0.25 documents verified — evidence supports the claim")
    elif _evidence_verdict == "PARTIAL_MATCH":
        _cf.append("+0.10 documents partially support the claim")
    elif _evidence_verdict == "MISMATCH":
        _cf.append("-0.25 submitted documents contradict the claim")
    elif _evidence_verdict in ("NO_DOCUMENTS", "CANNOT_VERIFY"):
        _cf.append("+0.00 no documents submitted or OCR unavailable")
    if fraud_flag and category in _FRAUD_CATEGORIES:
        if _fraud_signal_level in ("CRITICAL", "HIGH"):
            _cf.append("+0.15 high fraud signals consistent with fraud category")
        elif _fraud_signal_level == "MEDIUM":
            _cf.append("+0.08 moderate fraud signals aligned with category")
    elif fraud_flag and category not in _FRAUD_CATEGORIES:
        if _fraud_signal_level in ("CRITICAL", "HIGH"):
            _cf.append("-0.12 high fraud signals inconsistent with stated category")
    parsed["confidence_factors"] = _cf

    # ── Server-side risk tag enforcement ──────────────────────────────────────
    amount      = float(d.get("amount") or 0)
    tx_type     = (d.get("transaction_type") or "").upper()
    merchant_lc = (d.get("merchant") or "").lower()
    is_intl     = any(s in merchant_lc for s in _INTL_SIGNALS) or tx_type == "INTERNATIONAL"
    is_foreign  = (d.get("currency") or "INR").upper() != "INR"
    meta        = d.get("transaction_metadata") or {}

    def _meta_yes(k: str) -> bool:
        return str(meta.get(k) or "").strip().lower() in {"yes", "true", "1"}

    # Improved velocity signal detection
    _VELOCITY_SIGNALS = {
        "within", "multiple transaction", "charged twice", "charged again",
        "back to back", "repeated charge", "charged multiple",
        "two transaction", "three transaction",
    }
    _has_velocity = any(kw in comment_lc for kw in _VELOCITY_SIGNALS)

    tags = set(parsed.get("risk_tags") or [])

    # Known scam merchant keywords — MERCHANT_BLACKLISTED is only valid for these
    _SCAM_MERCHANT_SIGNALS = {
        "crypto", "bitcoin", "lottery", "prize", "lucky", "investment",
        "forex", "trading", "stock", "casino", "bet", "gambling",
        "ponzi", "scheme", "doubling", "forex",
    }
    _merchant_is_scam = any(s in merchant_lc for s in _SCAM_MERCHANT_SIGNALS)

    # Recurring/subscription signals in dispute reason or comment
    _RECURRING_SIGNALS = {
        "subscription", "recurring", "monthly", "auto-debit", "auto debit",
        "emi", "standing instruction", "repeat charge",
    }
    _dispute_reason_lc = (d.get("dispute_reason") or "").lower()
    _has_recurring = any(kw in comment_lc or kw in _dispute_reason_lc for kw in _RECURRING_SIGNALS)

    # Strip tags when deterministically invalid
    if amount < 50_000:
        tags.discard("HIGH_VALUE_TRANSACTION")
    if not (is_intl or is_foreign):
        tags.discard("INTERNATIONAL_TRANSACTION")
    if not fraud_flag:
        tags.discard("POSSIBLE_FRAUD")
    if not _has_velocity:
        tags.discard("VELOCITY_BREACH")
    if not _merchant_is_scam:
        tags.discard("MERCHANT_BLACKLISTED")
    if not _has_recurring:
        tags.discard("RECURRING_DISPUTE")

    # Enforce tags that must always be present when condition is true
    if amount >= 50_000:
        tags.add("HIGH_VALUE_TRANSACTION")
    if is_intl or is_foreign:
        tags.add("INTERNATIONAL_TRANSACTION")
    if fraud_flag:
        tags.add("POSSIBLE_FRAUD")
    if _meta_yes("sim_swap_suspected"):
        tags.add("SUSPICIOUS_BEHAVIOR")

    parsed["risk_tags"] = sorted(tags)
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

