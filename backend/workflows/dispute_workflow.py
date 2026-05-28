"""
LangGraph workflow for BFSI Dispute Resolution.

Graph topology:
  intake → validation → dispute_understanding → reasoning → structured_output → END

Each node appends to execution_trace for full audit traceability.
Conditional routing after validation allows early-exit on invalid inputs.
"""
import time
import operator
from typing import TypedDict, Optional, List, Annotated, Any
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END

from agents.dispute_understanding_agent import DisputeUnderstandingAgent
from utils.logger import workflow_logger, log_workflow_event
from utils.helpers import generate_case_id, utc_now_iso, sanitize_amount


# ── Workflow State ─────────────────────────────────────────────────────────────

class TraceEntry(TypedDict):
    node: str
    timestamp: str
    duration_ms: float
    success: bool
    details: str


class DisputeWorkflowState(TypedDict):
    # Raw intake
    dispute_input: dict

    # Validation
    validation_passed: bool
    validation_errors: List[str]
    validation_warnings: List[str]

    # AI analysis
    ai_analysis: Optional[dict]

    # Final output
    final_case: Optional[dict]

    # Execution metadata (list accumulates across nodes)
    execution_trace: Annotated[List[TraceEntry], operator.add]
    current_stage: str
    error_message: Optional[str]
    case_id: str


# ── Node helpers ──────────────────────────────────────────────────────────────

def _trace(node: str, start: float, success: bool, details: str = "") -> List[TraceEntry]:
    return [{
        "node": node,
        "timestamp": utc_now_iso(),
        "duration_ms": round((time.time() - start) * 1000, 2),
        "success": success,
        "details": details,
    }]


# ── Nodes ──────────────────────────────────────────────────────────────────────

def intake_node(state: DisputeWorkflowState) -> dict:
    """
    Parse and normalise raw intake form data.
    Assigns a case_id early so all downstream nodes and logs reference it.
    """
    start = time.time()
    node = "intake"

    dispute_input = state["dispute_input"].copy()

    # Normalise amount
    dispute_input["amount"] = sanitize_amount(dispute_input.get("amount", 0))

    # Assign case ID — use pre-generated ID from public submit endpoint if provided
    case_id = dispute_input.pop("_preset_case_id", None) or generate_case_id()
    dispute_input["case_id"] = case_id

    log_workflow_event(
        workflow_logger,
        event="NODE_INTAKE_COMPLETE",
        stage=node,
        case_id=case_id,
        customer_id=dispute_input.get("customer_id"),
    )

    return {
        "dispute_input": dispute_input,
        "case_id": case_id,
        "current_stage": node,
        "execution_trace": _trace(node, start, True, f"case_id={case_id} assigned"),
    }


def validation_node(state: DisputeWorkflowState) -> dict:
    """
    Business-rule validation of the dispute input.
    Checks completeness, amounts, date range, and spam signals.
    """
    start = time.time()
    node = "validation"
    d = state["dispute_input"]
    errors: List[str] = []
    warnings: List[str] = []

    # Required field checks
    required = ["customer_id", "transaction_id", "amount", "customer_comment", "dispute_reason"]
    for field in required:
        if not d.get(field):
            errors.append(f"Missing required field: {field}")

    # Amount validation
    amount = float(d.get("amount", 0))
    if amount <= 0:
        errors.append("Transaction amount must be greater than zero")
    if amount > 100_000_000:
        errors.append("Amount exceeds maximum allowable limit")

    # Comment length
    comment = str(d.get("customer_comment", ""))
    if len(comment) < 10:
        errors.append("Customer comment is too short to analyse")
    if comment.lower().strip() in {"test", "aaa", "xxx", "123", "na", "n/a"}:
        errors.append("Suspected test or spam submission")

    # High-value warning
    if amount > 500_000:
        warnings.append("Very high-value transaction — escalation may be required")

    passed = len(errors) == 0

    log_workflow_event(
        workflow_logger,
        event="NODE_VALIDATION_COMPLETE",
        stage=node,
        case_id=state.get("case_id"),
        extra={"passed": passed, "errors": errors, "warnings": warnings},
    )

    return {
        "validation_passed": passed,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "current_stage": node,
        "execution_trace": _trace(node, start, passed, f"passed={passed}, errors={len(errors)}"),
        "error_message": "; ".join(errors) if errors else None,
    }


def dispute_understanding_node(state: DisputeWorkflowState) -> dict:
    """
    Invokes the Dispute Understanding Agent (Groq LLM).
    Produces the AI analysis dict with all classification fields.
    """
    start = time.time()
    node = "dispute_understanding"

    agent = DisputeUnderstandingAgent()
    analysis = agent.analyze_dispute(state["dispute_input"])

    log_workflow_event(
        workflow_logger,
        event="NODE_AI_ANALYSIS_COMPLETE",
        stage=node,
        case_id=state.get("case_id"),
        extra={
            "category": analysis.get("dispute_category"),
            "confidence": analysis.get("confidence_score"),
        },
    )

    return {
        "ai_analysis": analysis,
        "current_stage": node,
        "execution_trace": _trace(
            node, start, True,
            f"category={analysis.get('dispute_category')} conf={analysis.get('confidence_score')}"
        ),
    }


def reasoning_node(state: DisputeWorkflowState) -> dict:
    """
    Post-process AI analysis: apply deterministic enrichment rules
    on top of LLM outputs to ensure BFSI compliance.
    """
    start = time.time()
    node = "reasoning"

    analysis = state["ai_analysis"].copy()
    d = state["dispute_input"]

    # Deterministic tag enrichment
    risk_tags: List[str] = list(analysis.get("risk_tags", []))
    amount = float(d.get("amount", 0))

    if amount > 50_000 and "HIGH_VALUE_TRANSACTION" not in risk_tags:
        risk_tags.append("HIGH_VALUE_TRANSACTION")
    if amount > 50_000 and "HIGH_PRIORITY_CASE" not in risk_tags:
        risk_tags.append("HIGH_PRIORITY_CASE")
    if analysis.get("fraud_suspicion") and "POSSIBLE_FRAUD" not in risk_tags:
        risk_tags.append("POSSIBLE_FRAUD")
    if d.get("fraud_selected") and "POSSIBLE_FRAUD" not in risk_tags:
        risk_tags.append("POSSIBLE_FRAUD")
    if d.get("transaction_type") in ("International", "Online Purchase") and "CARD_NOT_PRESENT" not in risk_tags:
        risk_tags.append("CARD_NOT_PRESENT")

    analysis["risk_tags"] = list(dict.fromkeys(risk_tags))  # deduplicate, preserve order

    log_workflow_event(
        workflow_logger,
        event="NODE_REASONING_COMPLETE",
        stage=node,
        case_id=state.get("case_id"),
        extra={"risk_tags": analysis["risk_tags"]},
    )

    return {
        "ai_analysis": analysis,
        "current_stage": node,
        "execution_trace": _trace(node, start, True, f"tags={len(analysis['risk_tags'])} enriched"),
    }


def structured_output_node(state: DisputeWorkflowState) -> dict:
    """
    Merge intake data + AI analysis into the canonical DisputeCase dict.
    This is the final output returned to the API layer.
    """
    start = time.time()
    node = "structured_output"

    d = state["dispute_input"]
    a = state["ai_analysis"]

    final_case = {
        # Identity
        "case_id": state["case_id"],
        "customer_id": d.get("customer_id", ""),
        "customer_name": d.get("customer_name", ""),
        "email": d.get("email", ""),
        "phone": d.get("phone", ""),
        # Transaction
        "transaction_id": d.get("transaction_id", ""),
        "transaction_type": d.get("transaction_type", ""),
        "merchant": d.get("merchant", ""),
        "amount": float(d.get("amount", 0)),
        "currency": d.get("currency", "INR"),
        "transaction_date": d.get("transaction_date", ""),
        "transaction_time": d.get("transaction_time", ""),
        # Customer input
        "customer_comment": d.get("customer_comment", ""),
        "dispute_reason": d.get("dispute_reason", ""),
        "fraud_selected": d.get("fraud_selected", False),
        # AI outputs
        "dispute_category": a.get("dispute_category", "Other"),
        "fraud_suspicion": a.get("fraud_suspicion", False),
        "customer_intent_summary": a.get("customer_intent_summary", ""),
        "priority": a.get("priority", "MEDIUM"),
        "confidence_score": a.get("confidence_score", 0.5),
        "risk_tags": a.get("risk_tags", []),
        "structured_reasoning": a.get("structured_reasoning", ""),
        # Workflow
        "status": "Dispute Raised",
        "workflow_ready": True,
        "current_stage": "completed",
        "execution_trace": state.get("execution_trace", []),
        "created_at": utc_now_iso(),
    }

    log_workflow_event(
        workflow_logger,
        event="WORKFLOW_COMPLETE",
        stage=node,
        case_id=state["case_id"],
        extra={"status": "Dispute Raised", "priority": final_case["priority"]},
    )

    return {
        "final_case": final_case,
        "current_stage": "completed",
        "execution_trace": _trace(node, start, True, "case ready for storage"),
    }


def invalid_submission_node(state: DisputeWorkflowState) -> dict:
    """Terminal node for submissions that failed validation."""
    start = time.time()
    node = "invalid_submission"

    errors = state.get("validation_errors", [])
    workflow_logger.warning(
        f"Dispute submission rejected — validation failed: {errors}",
        extra={"case_id": state.get("case_id"), "errors": errors},
    )

    return {
        "final_case": None,
        "current_stage": "rejected",
        "execution_trace": _trace(node, start, False, f"rejected: {'; '.join(errors)}"),
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_validation(state: DisputeWorkflowState) -> str:
    if state.get("validation_passed"):
        return "valid"
    return "invalid"


# ── Graph Assembly ────────────────────────────────────────────────────────────

def build_dispute_workflow() -> Any:
    """Compile and return the LangGraph dispute resolution workflow."""
    graph = StateGraph(DisputeWorkflowState)

    # Register nodes
    graph.add_node("intake", intake_node)
    graph.add_node("validation", validation_node)
    graph.add_node("dispute_understanding", dispute_understanding_node)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("structured_output", structured_output_node)
    graph.add_node("invalid_submission", invalid_submission_node)

    # Entry point
    graph.set_entry_point("intake")

    # Edges
    graph.add_edge("intake", "validation")

    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "valid": "dispute_understanding",
            "invalid": "invalid_submission",
        },
    )

    graph.add_edge("dispute_understanding", "reasoning")
    graph.add_edge("reasoning", "structured_output")
    graph.add_edge("structured_output", END)
    graph.add_edge("invalid_submission", END)

    compiled = graph.compile()
    workflow_logger.info("LangGraph dispute workflow compiled successfully")
    return compiled


# Singleton workflow instance (import and reuse across requests)
dispute_workflow = build_dispute_workflow()


def run_dispute_workflow(dispute_input: dict) -> dict:
    """
    Execute the dispute workflow for a given intake submission.

    Returns:
        dict with keys: final_case, validation_errors, execution_trace, current_stage
    """
    initial_state: DisputeWorkflowState = {
        "dispute_input": dispute_input,
        "validation_passed": False,
        "validation_errors": [],
        "validation_warnings": [],
        "ai_analysis": None,
        "final_case": None,
        "execution_trace": [],
        "current_stage": "start",
        "error_message": None,
        "case_id": "",
    }

    workflow_logger.info(
        "Starting dispute workflow",
        extra={"customer_id": dispute_input.get("customer_id")},
    )

    result = dispute_workflow.invoke(initial_state)
    return result
