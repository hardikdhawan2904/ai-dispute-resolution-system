"""
Deterministic pipeline nodes — each node calls its tool directly.
No LLM is used for routing. Only run_analysis_node triggers an LLM call.

Graph edges:
  validate → build_evidence → run_analysis → finalize → END
"""
import json

from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import (
    validate_dispute_input,
    build_evidence_summary,
    run_dispute_analysis,
    clamp_score,
    calculate_priority,
)
from utils.helpers import extract_json_from_text, utc_now_iso, generate_case_id
from utils.logger import agent_logger, log_workflow_event

_MAX_DOC_CHARS = 3000


def validate_node(state: DisputeAgentState) -> dict:
    d = state["dispute_input"]
    case_id = validate_dispute_input.invoke({
        "customer_id":      d.get("customer_id", ""),
        "existing_case_id": d.get("case_id", ""),
    })
    return {"case_id": case_id}


def build_evidence_node(state: DisputeAgentState) -> dict:
    d = state["dispute_input"]
    meta = d.get("transaction_metadata") or {}

    evidence = build_evidence_summary.invoke({"metadata_json": json.dumps(meta)})

    doc_texts = state.get("document_texts") or []
    if doc_texts:
        parts = []
        for i, t in enumerate(doc_texts):
            if t.strip():
                body = t[:_MAX_DOC_CHARS] + ("..." if len(t) > _MAX_DOC_CHARS else "")
                parts.append(f"Document {i + 1}:\n{body}")
        doc_section = "\n\n".join(parts) if parts else "No documents attached."
    else:
        doc_section = "No documents attached."

    return {"supporting_evidence": evidence, "document_section": doc_section}


def run_analysis_node(state: DisputeAgentState) -> dict:
    """Single LLM call — the only point in the pipeline where Groq is invoked."""
    d = state["dispute_input"]
    dispute_fields = {
        "customer_name":    d.get("customer_name", "Unknown"),
        "customer_id":      d.get("customer_id", ""),
        "transaction_type": d.get("transaction_type", ""),
        "merchant":         d.get("merchant", ""),
        "amount":           d.get("amount", 0),
        "currency":         d.get("currency", "INR"),
        "transaction_date": d.get("transaction_date", ""),
        "transaction_time": d.get("transaction_time", ""),
        "dispute_reason":   d.get("dispute_reason", ""),
        "fraud_selected":   d.get("fraud_selected", False),
        "customer_comment": d.get("customer_comment", ""),
    }
    raw = run_dispute_analysis.invoke({
        "case_id":            state["case_id"],
        "dispute_input_json": json.dumps(dispute_fields),
        "supporting_evidence": state["supporting_evidence"],
        "document_section":   state["document_section"],
    })
    return {"raw_llm_response": raw}


def finalize_node(state: DisputeAgentState) -> dict:
    d = state["dispute_input"]
    case_id = state.get("case_id") or d.get("case_id") or generate_case_id()
    raw = state.get("raw_llm_response", "")

    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("Failed to parse LLM JSON — using fallback", extra={"case_id": case_id})
        amount = float(d.get("amount", 0))
        fraud  = bool(d.get("fraud_selected", False))
        return {"final_case": {
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
            "priority":             calculate_priority.invoke({"amount": amount, "fraud_suspicion": fraud, "risk_tags": []}),
            "confidence_score":     0.1,
            "risk_tags":            ["HIGH_PRIORITY_CASE"] if fraud else [],
            "structured_reasoning": "AI analysis could not be completed. Manual investigation required.",
            "status":               "Dispute Raised",
            "workflow_ready":       True,
            "created_at":           utc_now_iso(),
        }}

    parsed["case_id"]        = case_id
    parsed["customer_id"]    = d.get("customer_id", "")
    parsed["transaction_id"] = d.get("transaction_id", "")
    parsed.setdefault("status",         "Dispute Raised")
    parsed.setdefault("workflow_ready", True)
    parsed.setdefault("created_at",     utc_now_iso())

    parsed["confidence_score"] = clamp_score.invoke(
        {"score": float(parsed.get("confidence_score", 0.5))}
    )

    valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    if parsed.get("priority") not in valid_priorities:
        parsed["priority"] = calculate_priority.invoke({
            "amount":          float(d.get("amount", 0)),
            "fraud_suspicion": parsed.get("fraud_suspicion", False),
            "risk_tags":       parsed.get("risk_tags", []),
        })

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
