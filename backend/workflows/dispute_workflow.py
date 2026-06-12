"""
LangGraph workflow for BFSI Dispute Resolution.

Graph topology:
  intake → validation → dispute_understanding → reasoning → investigation → structured_output → END

Each node appends to execution_trace for full audit traceability.
Conditional routing after validation allows early-exit on invalid inputs.
"""
import time
import operator
from typing import TypedDict, Optional, List, Annotated, Any
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END

from agents.dispute_agent import run_dispute_agent
from agents.investigation_agent import run_investigation_agent
from utils.logger import workflow_logger, log_workflow_event
from utils.helpers import generate_case_id, utc_now_iso, sanitize_amount
from services.dispute_understanding_fallback_service import classify_failure, generate_agent1_fallback


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
    document_texts: List[str]

    # Validation
    validation_passed: bool
    validation_errors: List[str]
    validation_warnings: List[str]

    # Document gate
    documents_sufficient: bool
    required_documents: List[str]

    # AI analysis
    ai_analysis: Optional[dict]

    # Investigation plan (Agent 2 output)
    investigation_output: Optional[dict]

    # Workflow plan (Agent 3 — WOA output)
    orchestration_output: Optional[dict]

    # Evidence assessment (Agent 4 — EIA output)
    evidence_output: Optional[dict]

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


def document_check_node(state: DisputeWorkflowState) -> dict:
    """
    Gate node — runs after validation.
    Determines required documents for this dispute and checks whether
    the customer submitted enough evidence to proceed with AI analysis.
    If insufficient, the case is saved as 'Pending Documents' and agents are skipped.
    """
    from services.document_rules import check_documents_sufficient, infer_category

    start = time.time()
    node  = "document_check"
    d     = state["dispute_input"]

    category = infer_category(d.get("dispute_reason", ""))
    fraud    = bool(d.get("fraud_selected", False))
    amount   = float(d.get("amount", 0))
    doc_count = int(d.get("_document_count", 0))

    sufficient, required_docs = check_documents_sufficient(category, fraud, amount, doc_count)

    log_workflow_event(
        workflow_logger,
        event="NODE_DOCUMENT_CHECK_COMPLETE",
        stage=node,
        case_id=state.get("case_id"),
        extra={"sufficient": sufficient, "doc_count": doc_count, "category": category},
    )

    return {
        "documents_sufficient": sufficient,
        "required_documents":   required_docs,
        "current_stage":        node,
        "execution_trace":      _trace(
            node, start, sufficient,
            f"sufficient={sufficient} doc_count={doc_count} min_required for '{category}'",
        ),
    }


def pending_documents_node(state: DisputeWorkflowState) -> dict:
    """
    Terminal node for cases that lack the minimum required evidence.
    Creates a persisted case with status 'Pending Documents' so the
    customer can be notified about what to submit — no AI analysis runs.
    """
    start = time.time()
    node  = "pending_documents"
    d     = state["dispute_input"]

    final_case = {
        "case_id":               state["case_id"],
        "customer_id":           d.get("customer_id", ""),
        "customer_name":         d.get("customer_name", ""),
        "email":                 d.get("email", ""),
        "phone":                 d.get("phone", ""),
        "transaction_id":        d.get("transaction_id", ""),
        "transaction_type":      d.get("transaction_type", ""),
        "merchant":              d.get("merchant", ""),
        "amount":                float(d.get("amount", 0)),
        "currency":              d.get("currency", "INR"),
        "transaction_date":      d.get("transaction_date", ""),
        "transaction_time":      d.get("transaction_time", ""),
        "customer_comment":      d.get("customer_comment", ""),
        "dispute_reason":        d.get("dispute_reason", ""),
        "fraud_selected":        d.get("fraud_selected", False),
        "transaction_metadata":  d.get("transaction_metadata") or {},
        # Not yet classified — pending documents
        "dispute_category":      None,
        "fraud_suspicion":       False,
        "customer_intent_summary": None,
        "confidence_score":      0.0,
        "confidence_factors":    [],
        "risk_tags":             [],
        "structured_reasoning":  None,
        "evidence_match":        None,
        "evidence_match_note":   None,
        "tools_used":            [],
        "agent_metadata":        None,
        "metrics":               None,
        "fallback_mode":         False,
        "failure_reason":        None,
        # Required documents stored so the customer and analyst see them
        "investigation_plan": {
            "required_documents": state.get("required_documents", []),
            "status_reason":      "Insufficient evidence submitted. Please upload the required documents to continue.",
        },
        "status":         "Pending Documents",
        "workflow_ready": False,
        "current_stage":  "pending_documents",
        "execution_trace": state.get("execution_trace", []),
        "created_at":     utc_now_iso(),
    }

    workflow_logger.warning(
        "Dispute halted — insufficient documents",
        extra={"case_id": state.get("case_id"), "required": state.get("required_documents", [])},
    )

    return {
        "final_case":    final_case,
        "current_stage": "pending_documents",
        "execution_trace": _trace(node, start, False, "halted — insufficient documents"),
    }


def _save_agent1_to_db(case_id: str, analysis: dict) -> None:
    """Intermediate DB save after Agent 1 — case visible with classification data."""
    if not case_id:
        return
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if case:
            case.dispute_category        = analysis.get("dispute_category")
            case.fraud_suspicion         = analysis.get("fraud_suspicion", False)
            case.confidence_score        = analysis.get("confidence_score", 0.0)
            case.risk_tags               = analysis.get("risk_tags", [])
            case.structured_reasoning    = analysis.get("structured_reasoning", "")
            case.customer_intent_summary = analysis.get("customer_intent_summary", "")
            case.evidence_match          = analysis.get("evidence_match")
            case.evidence_match_note     = analysis.get("evidence_match_note", "")
            case.confidence_factors      = analysis.get("confidence_factors") or []
            case.tools_used              = analysis.get("tools_used") or []
            case.agent_metadata          = analysis.get("agent_metadata")
            case.metrics                 = analysis.get("metrics")
            case.fallback_mode           = analysis.get("fallback_mode", False)
            case.failure_reason          = analysis.get("failure_reason")
            case.current_stage           = "agent1_complete"
            db.commit()
    except Exception as exc:
        workflow_logger.warning(f"Intermediate Agent 1 DB save failed for {case_id}: {exc}")
        db.rollback()
    finally:
        db.close()


def _save_agent2_to_db(case_id: str, investigation_plan: dict) -> None:
    """Intermediate DB save after Agent 2 — investigation plan available immediately."""
    if not case_id:
        return
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if case:
            case.investigation_plan = investigation_plan
            case.current_stage      = "agent2_complete"
            db.commit()
    except Exception as exc:
        workflow_logger.warning(f"Intermediate Agent 2 DB save failed for {case_id}: {exc}")
        db.rollback()
    finally:
        db.close()


def _save_agent3_to_db(case_id: str, workflow_plan: dict) -> None:
    """Intermediate DB save after Agent 3 — workflow plan available immediately."""
    if not case_id:
        return
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if case:
            case.workflow_plan  = workflow_plan
            case.current_stage  = "agent3_complete"
            db.commit()
    except Exception as exc:
        workflow_logger.warning(f"Intermediate Agent 3 DB save failed for {case_id}: {exc}")
        db.rollback()
    finally:
        db.close()


def _save_evidence_to_db(case_id: str, evidence_assessment: dict, workflow_plan: dict) -> None:
    """Intermediate DB save after Agent 4 — evidence assessment and updated workflow plan."""
    if not case_id:
        return
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if case:
            case.evidence_assessment = evidence_assessment
            # Update workflow_plan to mark EVIDENCE_AGENT as completed
            if isinstance(workflow_plan, dict) and workflow_plan:
                updated_plan = dict(workflow_plan)
                completed = list(updated_plan.get("completed_agents") or [])
                if "EVIDENCE_AGENT" not in completed:
                    completed.append("EVIDENCE_AGENT")
                updated_plan["completed_agents"] = completed
                # Advance next_agent past EVIDENCE_AGENT
                remaining = [
                    a for a in (updated_plan.get("workflow_path") or [])
                    if a not in completed
                ]
                updated_plan["remaining_agents"] = remaining
                updated_plan["next_agent"] = remaining[0] if remaining else None
                updated_plan["workflow_status"] = (
                    "IN_PROGRESS" if remaining else
                    ("ESCALATED" if updated_plan.get("escalation_required") else "COMPLETED")
                )
                case.workflow_plan = updated_plan
            case.current_stage = "agent4_complete"
            db.commit()
    except Exception as exc:
        workflow_logger.warning(f"Intermediate Agent 4 DB save failed for {case_id}: {exc}")
        db.rollback()
    finally:
        db.close()


def dispute_understanding_node(state: DisputeWorkflowState) -> dict:
    """
    Invokes the Dispute Understanding Agent (Groq LLM).
    Saves Agent 1 results to DB immediately after completion.
    """
    start = time.time()
    node  = "dispute_understanding"

    try:
        analysis = run_dispute_agent(
            state["dispute_input"],
            document_texts=state.get("document_texts") or [],
            case_id=state.get("case_id"),   # Agent 1 reads fresh from DB
        )
        # Do NOT save here — reasoning_node enriches risk_tags next.
        # _save_agent1_to_db is called at the end of reasoning_node so
        # Agent 2 reads the fully enriched data from DB.
        log_workflow_event(
            workflow_logger,
            event="NODE_AI_ANALYSIS_COMPLETE",
            stage=node,
            case_id=state.get("case_id"),
            extra={
                "category":   analysis.get("dispute_category"),
                "confidence": analysis.get("confidence_score"),
            },
        )
        return {
            "ai_analysis":     analysis,
            "current_stage":   node,
            "execution_trace": _trace(
                node, start, True,
                f"category={analysis.get('dispute_category')} conf={analysis.get('confidence_score')}",
            ),
        }

    except Exception as exc:
        # ── Agent 1 hard failure — generate safe fallback, never crash ────────
        duration_ms    = round((time.time() - start) * 1000, 1)
        failure_reason = classify_failure(exc)

        workflow_logger.error(
            f"Agent 1 (ARIA) failed — activating fallback. reason={failure_reason}",
            extra={
                "case_id":        state.get("case_id"),
                "failure_reason": failure_reason,
                "exc_type":       type(exc).__name__,
            },
            exc_info=True,
        )

        analysis = generate_agent1_fallback(
            state["dispute_input"],
            failure_reason=failure_reason,
            retry_count=3,
            duration_ms=duration_ms,
        )
        # Save fallback result so Agent 2 reads correct state from DB
        _save_agent1_to_db(state.get("case_id", ""), analysis)

        log_workflow_event(
            workflow_logger,
            event="AGENT1_FALLBACK_ACTIVATED",
            stage=node,
            case_id=state.get("case_id"),
            extra={
                "failure_reason": failure_reason,
                "exc_type":       type(exc).__name__,
                "duration_ms":    duration_ms,
            },
        )

        return {
            "ai_analysis":     analysis,
            "current_stage":   node,
            "execution_trace": _trace(
                node, start, False,
                f"FALLBACK activated — {failure_reason}: {type(exc).__name__}",
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

    # Save after reasoning so Agent 2 reads fully enriched tags from DB
    _save_agent1_to_db(state.get("case_id", ""), analysis)

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


def investigation_node(state: DisputeWorkflowState) -> dict:
    """
    Invokes the Investigation Intelligence Agent (IIA, Agent 2).
    Runs a ReAct loop with 5 investigative tools and returns a complete
    investigation plan: queue, complexity, risk profiles, document checklist, steps.
    """
    start = time.time()
    node = "investigation"

    try:
        # Agent 2 reads Agent 1 results from DB (reasoning-enriched) — not in-memory dict
        investigation_plan = run_investigation_agent({"case_id": state.get("case_id", "")})
        # Intermediate save — investigation plan available in DB immediately
        _save_agent2_to_db(state.get("case_id", ""), investigation_plan)
        log_workflow_event(
            workflow_logger,
            event="NODE_INVESTIGATION_COMPLETE",
            stage=node,
            case_id=state.get("case_id"),
            extra={
                "recommended_queue":        investigation_plan.get("recommended_queue"),
                "investigation_complexity": investigation_plan.get("investigation_complexity"),
                "duplicate_found":          investigation_plan.get("duplicate_found"),
            },
        )
        return {
            "investigation_output": investigation_plan,
            "current_stage": node,
            "execution_trace": _trace(
                node, start, True,
                f"queue={investigation_plan.get('recommended_queue')} "
                f"complexity={investigation_plan.get('investigation_complexity')}"
            ),
        }
    except Exception as exc:
        workflow_logger.warning(f"Investigation agent failed: {exc}", exc_info=True)
        return {
            "investigation_output": None,
            "current_stage": node,
            "execution_trace": _trace(node, start, False, f"agent failed: {exc}"),
        }


def orchestration_node(state: DisputeWorkflowState) -> dict:
    """
    Invokes the Workflow Orchestration Agent (WOA, Agent 3).
    Reads Agent 1 + Agent 2 results from DB, determines required specialist
    agents, generates workflow path, and identifies the next execution step.
    """
    from agents.orchestration_agent import run_orchestration_agent

    start = time.time()
    node  = "orchestration"

    try:
        workflow_plan = run_orchestration_agent(state.get("case_id", ""))
        # Intermediate save — workflow plan available in DB immediately
        _save_agent3_to_db(state.get("case_id", ""), workflow_plan)
        log_workflow_event(
            workflow_logger,
            event="NODE_ORCHESTRATION_COMPLETE",
            stage=node,
            case_id=state.get("case_id"),
            extra={
                "workflow_complexity": workflow_plan.get("workflow_complexity"),
                "required_agents":     workflow_plan.get("required_agents"),
                "next_agent":          workflow_plan.get("next_agent"),
                "escalation_required": workflow_plan.get("escalation_required"),
            },
        )
        return {
            "orchestration_output": workflow_plan,
            "current_stage":        node,
            "execution_trace":      _trace(
                node, start, True,
                f"complexity={workflow_plan.get('workflow_complexity')} "
                f"next={workflow_plan.get('next_agent')} "
                f"agents={workflow_plan.get('required_agents')}"
            ),
        }
    except Exception as exc:
        workflow_logger.warning(f"Orchestration agent failed: {exc}", exc_info=True)
        return {
            "orchestration_output": None,
            "current_stage":        node,
            "execution_trace":      _trace(node, start, False, f"agent failed: {exc}"),
        }


def evidence_node(state: DisputeWorkflowState) -> dict:
    """
    Invokes the Evidence Intelligence Agent (EIA, Agent 4).
    Only runs when WOA has routed to EVIDENCE_AGENT.
    Reads all case data from DB, assesses evidence completeness/strength/consistency,
    and saves the evidence_assessment to DB.
    """
    from agents.evidence_agent import run_evidence_agent

    start = time.time()
    node  = "evidence"

    try:
        evidence_assessment = run_evidence_agent(state.get("case_id", ""))
        # Intermediate save — evidence assessment and updated workflow plan
        orchestration_output = state.get("orchestration_output") or {}
        _save_evidence_to_db(state.get("case_id", ""), evidence_assessment, orchestration_output)
        log_workflow_event(
            workflow_logger,
            event="NODE_EVIDENCE_COMPLETE",
            stage=node,
            case_id=state.get("case_id"),
            extra={
                "evidence_completeness": evidence_assessment.get("evidence_completeness"),
                "evidence_strength":     evidence_assessment.get("evidence_strength"),
                "investigation_blocked": evidence_assessment.get("investigation_blocked"),
                "missing_docs":          len(evidence_assessment.get("missing_documents", [])),
            },
        )
        return {
            "evidence_output": evidence_assessment,
            "current_stage":   node,
            "execution_trace": _trace(
                node, start, True,
                f"strength={evidence_assessment.get('evidence_strength')} "
                f"completeness={evidence_assessment.get('evidence_completeness')} "
                f"blocked={evidence_assessment.get('investigation_blocked')}"
            ),
        }
    except Exception as exc:
        workflow_logger.warning(f"Evidence agent failed: {exc}", exc_info=True)
        return {
            "evidence_output": None,
            "current_stage":   node,
            "execution_trace": _trace(node, start, False, f"agent failed: {exc}"),
        }


def route_after_orchestration(state: DisputeWorkflowState) -> str:
    """Route to evidence_node only when WOA designates EVIDENCE_AGENT as the immediate
    next step. Respects dependency ordering — if FRAUD_AGENT must run first, WOA sets
    next_agent=FRAUD_AGENT and EIA is skipped for this run (analyst triggers it later)."""
    wf_plan    = state.get("orchestration_output") or {}
    next_agent = wf_plan.get("next_agent") if isinstance(wf_plan, dict) else None
    return "run_evidence" if next_agent == "EVIDENCE_AGENT" else "skip_evidence"


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
        "confidence_score": a.get("confidence_score", 0.5),
        "confidence_factors": a.get("confidence_factors", []),
        "risk_tags": a.get("risk_tags", []),
        "structured_reasoning": a.get("structured_reasoning", ""),
        "evidence_match": a.get("evidence_match"),
        "evidence_match_note": a.get("evidence_match_note", ""),
        # Agent 1 audit trail
        "tools_used":     a.get("tools_used", []),
        "agent_metadata": a.get("agent_metadata", {}),
        "metrics":        a.get("metrics", {}),
        # Agent 1 fallback resilience flags (Changes 3 & 4)
        "fallback_mode":  a.get("fallback_mode", False),
        "failure_reason": a.get("failure_reason"),
        # Supporting evidence (preserved for re-analysis)
        "transaction_metadata": d.get("transaction_metadata") or {},
        # Investigation plan (Agent 2)
        "investigation_plan": state.get("investigation_output"),
        # Workflow plan (Agent 3 — WOA)
        "workflow_plan": state.get("orchestration_output"),
        # Evidence assessment (Agent 4 — EIA)
        "evidence_assessment": state.get("evidence_output"),
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
        extra={"status": "Dispute Raised", "category": final_case.get("dispute_category")},
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


def route_after_document_check(state: DisputeWorkflowState) -> str:
    if state.get("documents_sufficient"):
        return "sufficient"
    return "insufficient"


# ── Graph Assembly ────────────────────────────────────────────────────────────

def build_dispute_workflow() -> Any:
    """Compile and return the LangGraph dispute resolution workflow."""
    graph = StateGraph(DisputeWorkflowState)

    # Register nodes
    graph.add_node("intake",               intake_node)
    graph.add_node("validation",           validation_node)
    graph.add_node("document_check",       document_check_node)
    graph.add_node("pending_documents",    pending_documents_node)
    graph.add_node("dispute_understanding", dispute_understanding_node)
    graph.add_node("reasoning",            reasoning_node)
    graph.add_node("investigation",        investigation_node)
    graph.add_node("orchestration",        orchestration_node)
    graph.add_node("evidence",             evidence_node)
    graph.add_node("structured_output",    structured_output_node)
    graph.add_node("invalid_submission",   invalid_submission_node)

    # Entry point
    graph.set_entry_point("intake")

    # Edges
    graph.add_edge("intake", "validation")

    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "valid":   "document_check",
            "invalid": "invalid_submission",
        },
    )

    graph.add_conditional_edges(
        "document_check",
        route_after_document_check,
        {
            "sufficient":   "dispute_understanding",
            "insufficient": "pending_documents",
        },
    )

    graph.add_edge("dispute_understanding", "reasoning")
    graph.add_edge("reasoning",             "investigation")
    graph.add_edge("investigation",         "orchestration")
    # After orchestration: route to evidence agent if WOA requires it
    graph.add_conditional_edges(
        "orchestration",
        route_after_orchestration,
        {
            "run_evidence":  "evidence",
            "skip_evidence": "structured_output",
        },
    )
    graph.add_edge("evidence",          "structured_output")
    graph.add_edge("structured_output", END)
    graph.add_edge("pending_documents", END)
    graph.add_edge("invalid_submission", END)

    compiled = graph.compile()
    workflow_logger.info("LangGraph dispute workflow compiled successfully")
    return compiled


# Singleton workflow instance (import and reuse across requests)
dispute_workflow = build_dispute_workflow()


def run_dispute_workflow(dispute_input: dict, document_texts: Optional[List[str]] = None) -> dict:
    """
    Execute the dispute workflow for a given intake submission.
    document_texts: evidence file text extracted before calling the LLM.

    Returns:
        dict with keys: final_case, validation_errors, execution_trace, current_stage
    """
    initial_state: DisputeWorkflowState = {
        "dispute_input":        dispute_input,
        "document_texts":       document_texts or [],
        "validation_passed":    False,
        "validation_errors":    [],
        "validation_warnings":  [],
        "documents_sufficient": True,
        "required_documents":   [],
        "ai_analysis":          None,
        "investigation_output": None,
        "orchestration_output": None,
        "evidence_output":      None,
        "final_case":           None,
        "execution_trace":      [],
        "current_stage":        "start",
        "error_message":        None,
        "case_id":              "",
    }

    workflow_logger.info(
        "Starting dispute workflow",
        extra={"customer_id": dispute_input.get("customer_id")},
    )

    try:
        result = dispute_workflow.invoke(initial_state)
        return result
    except Exception as exc:
        # Last-resort catch — should never reach here after node-level fallbacks,
        # but prevents a 500 from propagating to the API under any circumstance.
        case_id        = dispute_input.get("_preset_case_id") or dispute_input.get("case_id") or ""
        failure_reason = classify_failure(exc)
        workflow_logger.error(
            f"Dispute workflow crashed unexpectedly — activating service-level fallback. reason={failure_reason}",
            extra={"case_id": case_id, "failure_reason": failure_reason, "exc_type": type(exc).__name__},
            exc_info=True,
        )
        fallback_analysis = generate_agent1_fallback(
            dispute_input, failure_reason=failure_reason, retry_count=3,
        )
        _save_agent1_to_db(case_id, fallback_analysis)
        # Build a minimal final_case so the case always gets persisted
        d = dispute_input
        final_case = {
            **fallback_analysis,
            "customer_name":      d.get("customer_name", ""),
            "email":              d.get("email", ""),
            "phone":              d.get("phone", ""),
            "transaction_date":   d.get("transaction_date", ""),
            "transaction_time":   d.get("transaction_time", ""),
            "customer_comment":   d.get("customer_comment", ""),
            "dispute_reason":     d.get("dispute_reason", ""),
            "fraud_selected":     d.get("fraud_selected", False),
            "transaction_metadata": d.get("transaction_metadata") or {},
            "investigation_plan": None,
            "status":             "Dispute Raised",
            "workflow_ready":     True,
        }
        return {
            "dispute_input":       dispute_input,
            "document_texts":      document_texts or [],
            "validation_passed":   True,
            "validation_errors":   [],
            "validation_warnings": [],
            "ai_analysis":         fallback_analysis,
            "investigation_output": None,
            "final_case":          final_case,
            "execution_trace":     [],
            "current_stage":       "fallback",
            "error_message":       f"Workflow crashed: {failure_reason}",
            "case_id":             case_id,
        }
