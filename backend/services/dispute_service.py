"""
DisputeService — orchestrates workflow execution and database persistence.

Save-first architecture:
  1. Case saved to DB immediately on submission (visible in queue, workflow_ready=False)
  2. Agent 1 runs → intermediate DB save (classification fields)
  3. Agent 2 runs → intermediate DB save (investigation_plan)
  4. Final enrichment → DB update (priority, queue, SLA, status)
  5. workflow_ready=True

This means the case is always recoverable, always visible during processing,
and analysts can see progress in real-time.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from workflows.dispute_workflow import run_dispute_workflow
from database.models import DisputeCase, AuditLog, WorkflowState
from utils.logger import api_logger, audit_logger, log_workflow_event
from utils.helpers import utc_now_iso, generate_case_id
from services.priority_engine import compute_priority
from services.sla_service import compute_sla_deadline
from services.queue_assignment_service import assign_queue
from services.duplicate_detection_service import find_duplicate
from services.manual_review_service import should_flag_manual_review
from services.data_sync_service import sync_on_submission, sync_on_resolution
from services.communication_service import trigger_communication_async


class DisputeService:

    # ── Submission ─────────────────────────────────────────────────────────────

    @staticmethod
    def submit_dispute(dispute_input: dict, db: Session, document_texts: Optional[List[str]] = None) -> dict:
        """
        Save-first dispute submission pipeline:
          1. Save preliminary case to DB immediately (visible in queue)
          2. Run LangGraph workflow — nodes save intermediate results to DB
          3. Enrich with priority/queue/SLA and update DB record
          4. Audit logs + workflow state snapshots
        """
        audit_logger.info(
            "Dispute submission received",
            extra={
                "customer_id": dispute_input.get("customer_id"),
                "transaction_id": dispute_input.get("transaction_id"),
            },
        )

        # Ensure case_id is populated in dispute_input before preliminary save
        if "case_id" not in dispute_input:
            dispute_input["case_id"] = dispute_input.get("_preset_case_id") or generate_case_id(db)

        # ── Step 1: Save to DB immediately ────────────────────────────────────
        db_case = DisputeService._save_preliminary_case(dispute_input, db)
        DisputeService._append_audit_log(
            db=db, case_id=db_case.case_id,
            event_type="CASE_RECEIVED", stage="intake",
            message="Case received and saved to database. Analysis pipeline starting.",
            payload={"customer_id": dispute_input.get("customer_id"), "transaction_id": dispute_input.get("transaction_id")},
        )
        db.commit()
        # CCA — notify customer that dispute was received
        try:
            trigger_communication_async(db_case.case_id, "CASE_RECEIVED")
        except Exception:
            pass

        # ── Step 2: Run LangGraph workflow (agents save intermediate results) ──
        workflow_result = run_dispute_workflow(
            dispute_input,
            document_texts=document_texts or [],
        )
        final_case      = workflow_result.get("final_case")
        validation_errors  = workflow_result.get("validation_errors", [])
        execution_trace = workflow_result.get("execution_trace", [])

        if not final_case:
            # Validation failed — mark the already-saved case as rejected
            db_case.status        = "Rejected"
            db_case.workflow_ready = False
            DisputeService._append_audit_log(
                db=db, case_id=db_case.case_id,
                event_type="VALIDATION_FAILED", stage="validation",
                message=f"Submission rejected: {'; '.join(validation_errors)}",
                payload={"errors": validation_errors},
            )
            db.commit()
            audit_logger.warning("Dispute rejected — validation failed", extra={"errors": validation_errors})
            return {
                "success": False,
                "errors": validation_errors,
                "case_id": db_case.case_id,
                "final_case": None,
            }

        # ── Step 3: Enterprise enrichment ─────────────────────────────────────
        priority_score, priority_label = compute_priority(final_case)
        final_case["priority"]       = priority_label
        final_case["priority_score"] = priority_score

        queue = assign_queue(final_case)
        final_case["assigned_queue"] = queue

        sla_deadline = compute_sla_deadline(priority_label)
        final_case["sla_deadline"] = sla_deadline

        manual_flag, manual_reason = should_flag_manual_review(final_case)
        final_case["requires_manual_review"] = manual_flag
        final_case["manual_review_reason"]   = manual_reason if manual_flag else None

        if final_case.get("fallback_mode"):
            failure_reason = final_case.get("failure_reason", "UNKNOWN_ERROR")
            final_case["requires_manual_review"] = True
            final_case["manual_review_reason"] = (
                f"AI service was unavailable at submission time (failure: {failure_reason}). "
                "Automated dispute classification could not be completed — manual investigation required."
            )

        # Status: based on whether documents were submitted with the form
        inv_plan = final_case.get("investigation_plan") or {}
        has_required_docs   = isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents"))
        documents_submitted = bool(document_texts)

        if documents_submitted:
            final_case["status"] = "Under Investigation"
        elif has_required_docs:
            final_case["status"] = "Pending Documents"
        else:
            final_case["status"] = "Dispute Raised"

        # ── Step 4: Update the existing DB record with full results ────────────
        DisputeService._update_case_with_results(db_case, final_case, db)

        # Sync to transactions + merchant_profiles
        sync_on_submission(db_case, db)

        # Duplicate detection
        dup_of = find_duplicate(
            db_case.customer_id, db_case.transaction_id,
            db_case.amount, db_case.merchant or "", db,
            exclude_case_id=db_case.case_id,
        )
        if dup_of:
            db_case.duplicate_of = dup_of
            DisputeService._append_audit_log(
                db=db, case_id=db_case.case_id,
                event_type="DUPLICATE_DETECTED", stage="post_analysis",
                message=f"Possible duplicate of case {dup_of}",
                payload={"duplicate_of": dup_of},
            )

        if manual_flag or final_case.get("fallback_mode"):
            reason_msg = final_case.get("manual_review_reason") or manual_reason or ""
            DisputeService._append_audit_log(
                db=db, case_id=db_case.case_id,
                event_type="MANUAL_REVIEW_FLAGGED", stage="post_analysis",
                message=reason_msg,
                payload={"reason": reason_msg},
            )

        if final_case.get("fallback_mode"):
            failure_reason = final_case.get("failure_reason", "UNKNOWN_ERROR")
            DisputeService._append_audit_log(
                db=db, case_id=db_case.case_id,
                event_type="AGENT1_FALLBACK_ACTIVATED", stage="dispute_understanding",
                message=(
                    f"Agent 1 (ARIA) was unavailable — fallback mode activated. "
                    f"Failure reason: {failure_reason}. Manual review required."
                ),
                payload={
                    "fallback_mode":    True,
                    "failure_reason":   failure_reason,
                    "confidence_score": final_case.get("confidence_score", 0.1),
                    "retry_count":      (final_case.get("metrics") or {}).get("retry_count", 3),
                },
            )

        DisputeService._append_audit_log(
            db=db, case_id=db_case.case_id,
            event_type="CASE_CREATED", stage="structured_output",
            message=f"Analysis complete. Category: {db_case.dispute_category}, Priority: {db_case.priority}",
            payload={
                "confidence_score": db_case.confidence_score,
                "risk_tags":        db_case.risk_tags,
                "assigned_queue":   queue,
                "priority_score":   priority_score,
            },
        )

        DisputeService._persist_workflow_states(db, db_case.case_id, execution_trace)

        db.commit()

        audit_logger.info(
            "Dispute case analysis complete",
            extra={"case_id": db_case.case_id, "priority": db_case.priority},
        )

        # DOCUMENT_REQUESTED is sent by document_request_service when analyst
        # formally creates a request — not auto-sent here to avoid noise.

        return {
            "success": True,
            "errors": [],
            "case_id": db_case.case_id,
            "final_case": db_case.to_dict(),
        }

    @staticmethod
    def run_pipeline(dispute_input: dict, document_texts: List[str]) -> dict:
        """
        Run Steps 2-4 of the submission pipeline in the background.
        Creates its own DB session so it can run after the HTTP response has been sent.
        """
        from database.database import SessionLocal
        from database.models import DisputeCase
        db = SessionLocal()
        try:
            case_id = dispute_input["case_id"]
            db_case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
            if not db_case:
                api_logger.error(f"run_pipeline: case {case_id} not found in DB")
                return {"success": False}

            # Step 2: Run LangGraph workflow
            workflow_result    = run_dispute_workflow(dispute_input, document_texts=document_texts)
            final_case         = workflow_result.get("final_case")
            validation_errors  = workflow_result.get("validation_errors", [])
            execution_trace    = workflow_result.get("execution_trace", [])

            if not final_case:
                db_case.status         = "Rejected"
                db_case.workflow_ready = False
                DisputeService._append_audit_log(
                    db=db, case_id=case_id,
                    event_type="VALIDATION_FAILED", stage="validation",
                    message=f"Submission rejected: {'; '.join(validation_errors)}",
                    payload={"errors": validation_errors},
                )
                db.commit()
                return {"success": False, "errors": validation_errors}

            # Step 3: Enterprise enrichment
            priority_score, priority_label = compute_priority(final_case)
            final_case["priority"]         = priority_label
            final_case["priority_score"]   = priority_score
            queue                          = assign_queue(final_case)
            final_case["assigned_queue"]   = queue
            sla_deadline                   = compute_sla_deadline(priority_label)
            final_case["sla_deadline"]     = sla_deadline
            manual_flag, manual_reason     = should_flag_manual_review(final_case)
            final_case["requires_manual_review"] = manual_flag
            final_case["manual_review_reason"]   = manual_reason if manual_flag else None

            if final_case.get("fallback_mode"):
                failure_reason = final_case.get("failure_reason", "UNKNOWN_ERROR")
                final_case["requires_manual_review"] = True
                final_case["manual_review_reason"] = (
                    f"AI service was unavailable at submission time (failure: {failure_reason}). "
                    "Automated dispute classification could not be completed — manual investigation required."
                )

            inv_plan            = final_case.get("investigation_plan") or {}
            has_required_docs   = isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents"))
            documents_submitted = bool(document_texts)
            if documents_submitted:
                final_case["status"] = "Under Investigation"
            elif has_required_docs:
                final_case["status"] = "Pending Documents"
            else:
                final_case["status"] = "Dispute Raised"

            # Step 4: Update DB record with full results
            DisputeService._update_case_with_results(db_case, final_case, db)
            sync_on_submission(db_case, db)

            dup_of = find_duplicate(
                db_case.customer_id, db_case.transaction_id,
                db_case.amount, db_case.merchant or "", db,
                exclude_case_id=case_id,
            )
            if dup_of:
                db_case.duplicate_of = dup_of
                DisputeService._append_audit_log(
                    db=db, case_id=case_id,
                    event_type="DUPLICATE_DETECTED", stage="post_analysis",
                    message=f"Possible duplicate of case {dup_of}",
                    payload={"duplicate_of": dup_of},
                )

            if manual_flag or final_case.get("fallback_mode"):
                reason_msg = final_case.get("manual_review_reason") or manual_reason or ""
                DisputeService._append_audit_log(
                    db=db, case_id=case_id,
                    event_type="MANUAL_REVIEW_FLAGGED", stage="post_analysis",
                    message=reason_msg, payload={"reason": reason_msg},
                )

            if final_case.get("fallback_mode"):
                failure_reason = final_case.get("failure_reason", "UNKNOWN_ERROR")
                DisputeService._append_audit_log(
                    db=db, case_id=case_id,
                    event_type="AGENT1_FALLBACK_ACTIVATED", stage="dispute_understanding",
                    message=f"Agent 1 (ARIA) fallback activated. Failure: {failure_reason}.",
                    payload={"fallback_mode": True, "failure_reason": failure_reason},
                )

            DisputeService._append_audit_log(
                db=db, case_id=case_id,
                event_type="CASE_CREATED", stage="structured_output",
                message=f"Analysis complete. Category: {db_case.dispute_category}, Priority: {db_case.priority}",
                payload={"confidence_score": db_case.confidence_score,
                         "risk_tags": db_case.risk_tags, "assigned_queue": queue,
                         "priority_score": priority_score},
            )
            DisputeService._persist_workflow_states(db, case_id, execution_trace)
            db.commit()

            # DOCUMENT_REQUESTED sent by analyst via document_request_service, not here.

            audit_logger.info("Background pipeline complete", extra={"case_id": case_id})
            return {"success": True, "case_id": case_id, "final_case": db_case.to_dict()}

        except Exception as exc:
            api_logger.error(f"run_pipeline error for {dispute_input.get('case_id')}: {exc}", exc_info=True)
            db.rollback()
            return {"success": False}
        finally:
            db.close()

    # ── Retrieval ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_case(case_id: str, db: Session) -> Optional[dict]:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        return case.to_dict() if case else None

    @staticmethod
    def list_cases(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        fraud_only: bool = False,
    ) -> dict:
        query = db.query(DisputeCase)
        if status:
            query = query.filter(DisputeCase.status == status)
        if priority:
            query = query.filter(DisputeCase.priority == priority)
        if category:
            query = query.filter(DisputeCase.dispute_category == category)
        if fraud_only:
            query = query.filter(DisputeCase.fraud_suspicion == True)

        total = query.count()
        cases = query.order_by(desc(DisputeCase.created_at)).offset(skip).limit(limit).all()
        return {"total": total, "cases": [c.to_dict() for c in cases]}

    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        total      = db.query(DisputeCase).count()
        open_cases = db.query(DisputeCase).filter(
            DisputeCase.status.in_(["Dispute Raised", "Under Investigation", "Pending Documents"])
        ).count()
        fraud_cases    = db.query(DisputeCase).filter(DisputeCase.fraud_suspicion == True).count()
        critical_cases = db.query(DisputeCase).filter(DisputeCase.priority == "CRITICAL").count()
        avg_conf       = db.query(func.avg(DisputeCase.confidence_score)).scalar() or 0.0

        cat_rows  = db.query(DisputeCase.dispute_category, func.count()).group_by(DisputeCase.dispute_category).all()
        pri_rows  = db.query(DisputeCase.priority,         func.count()).group_by(DisputeCase.priority).all()
        stat_rows = db.query(DisputeCase.status,           func.count()).group_by(DisputeCase.status).all()
        recent    = db.query(DisputeCase).order_by(desc(DisputeCase.created_at)).limit(5).all()

        return {
            "total_cases":         total,
            "open_cases":          open_cases,
            "fraud_cases":         fraud_cases,
            "critical_cases":      critical_cases,
            "avg_confidence_score": round(float(avg_conf), 3),
            "cases_by_category":   {r[0]: r[1] for r in cat_rows  if r[0]},
            "cases_by_priority":   {r[0]: r[1] for r in pri_rows  if r[0]},
            "cases_by_status":     {r[0]: r[1] for r in stat_rows if r[0]},
            "recent_cases":        [c.to_dict() for c in recent],
        }

    @staticmethod
    def get_audit_logs(case_id: str, db: Session) -> List[dict]:
        logs = db.query(AuditLog).filter(AuditLog.case_id == case_id).order_by(AuditLog.created_at).all()
        return [log.to_dict() for log in logs]

    @staticmethod
    def get_workflow_states(case_id: str, db: Session) -> List[dict]:
        states = (
            db.query(WorkflowState)
            .filter(WorkflowState.case_id == case_id)
            .order_by(WorkflowState.created_at)
            .all()
        )
        return [s.to_dict() for s in states]

    # ── Mutation ───────────────────────────────────────────────────────────────

    @staticmethod
    def update_status(case_id: str, new_status: str, actor: str, note: Optional[str], db: Session) -> Optional[dict]:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return None

        old_status  = case.status
        case.status = new_status
        case.updated_at = datetime.now(timezone.utc)

        DisputeService._append_audit_log(
            db=db, case_id=case_id,
            event_type="STATUS_CHANGED", stage="manual_update", actor=actor,
            message=f"Status changed from '{old_status}' to '{new_status}'",
            payload={"note": note, "actor": actor},
        )

        sync_on_resolution(case, db)
        db.commit()
        db.refresh(case)

        # CCA — only fire for major customer-visible stage transitions.
        # Skip if status hasn't actually changed, or if it's an internal-only transition.
        _MAJOR_CUSTOMER_STAGES = {
            "Dispute Raised", "Under Investigation", "Pending Documents",
            "Escalated", "Resolved", "Rejected", "Closed",
        }
        try:
            if new_status != old_status and new_status in _MAJOR_CUSTOMER_STAGES:
                _STATUS_COMM_MAP = {
                    "Under Investigation": "INVESTIGATION_STARTED",
                    "Pending Documents":   "DOCUMENT_REQUESTED",
                    "Resolved":            "CASE_RESOLVED",
                    "Rejected":            "CASE_RESOLVED",
                    "Closed":              "CASE_RESOLVED",
                    "Escalated":           "STATUS_CHANGED",
                    "Dispute Raised":      "STATUS_CHANGED",
                }
                comm_type = _STATUS_COMM_MAP.get(new_status, "STATUS_CHANGED")
                context = {"new_status": new_status, "resolution_status": new_status}
                if note:
                    context["resolution_summary"] = note
                trigger_communication_async(case_id, comm_type, context=context)
        except Exception:
            pass

        return case.to_dict()

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _save_preliminary_case(dispute_input: dict, db: Session) -> DisputeCase:
        """
        Persist the case immediately on submission with form data only.
        AI fields are left at defaults — they are filled in by the workflow nodes
        and _update_case_with_results() as the pipeline progresses.
        """
        db_case = DisputeCase(
            case_id          = dispute_input["case_id"],
            customer_id      = dispute_input.get("customer_id", ""),
            customer_name    = dispute_input.get("customer_name", ""),
            email            = dispute_input.get("email", ""),
            phone            = dispute_input.get("phone", ""),
            transaction_id   = dispute_input.get("transaction_id", ""),
            transaction_type = dispute_input.get("transaction_type", ""),
            merchant         = dispute_input.get("merchant", ""),
            amount           = dispute_input.get("amount", 0),
            currency         = dispute_input.get("currency", "INR"),
            transaction_date = dispute_input.get("transaction_date", ""),
            transaction_time = dispute_input.get("transaction_time", ""),
            customer_comment = dispute_input.get("customer_comment", ""),
            dispute_reason   = dispute_input.get("dispute_reason", ""),
            fraud_selected   = dispute_input.get("fraud_selected", False),
            transaction_metadata = dispute_input.get("transaction_metadata") or {},
            # Defaults until agents fill them in
            trust_intelligence    = None,
            user_trust_score      = 1.0,
            behavioral_risk_score = 0.0,
            identity_status       = "PENDING",
            fraud_reasoning_brief = None,
            fraud_probability     = 0.0,
            fraud_risk_level      = "LOW",
            status           = "Dispute Raised",
            workflow_ready   = False,   # ← not complete yet
            current_stage    = "intake",
            priority         = "MEDIUM",
            priority_score   = 0.0,
            confidence_score = 0.0,
            fraud_suspicion  = False,
            risk_tags        = [],
            confidence_factors = [],
            tools_used       = [],
            sla_breached     = False,
            requires_manual_review = False,
            fallback_mode    = False,
        )
        db.add(db_case)
        db.flush()
        return db_case

    @staticmethod
    def _update_case_with_results(db_case: DisputeCase, final_case: dict, db: Session) -> None:
        """
        Update the preliminary case record with the full AI analysis results.
        Called after the workflow completes and enterprise enrichment is applied.
        """
        db_case.dispute_category        = final_case.get("dispute_category", "Other")
        db_case.fraud_suspicion         = final_case.get("fraud_suspicion", False)
        db_case.customer_intent_summary = final_case.get("customer_intent_summary", "")
        db_case.priority                = final_case.get("priority", "MEDIUM")
        db_case.confidence_score        = final_case.get("confidence_score", 0.5)
        db_case.risk_tags               = final_case.get("risk_tags", [])
        db_case.structured_reasoning    = final_case.get("structured_reasoning", "")
        db_case.evidence_match          = final_case.get("evidence_match")
        db_case.evidence_match_note     = final_case.get("evidence_match_note", "")
        db_case.assigned_queue          = final_case.get("assigned_queue")
        db_case.priority_score          = final_case.get("priority_score", 0.0)
        db_case.sla_deadline            = final_case.get("sla_deadline")
        db_case.requires_manual_review  = final_case.get("requires_manual_review", False)
        db_case.manual_review_reason    = final_case.get("manual_review_reason")
        db_case.investigation_plan      = final_case.get("investigation_plan")
        db_case.confidence_factors      = final_case.get("confidence_factors") or []
        db_case.tools_used              = final_case.get("tools_used") or []
        db_case.agent_metadata          = final_case.get("agent_metadata")
        db_case.metrics                 = final_case.get("metrics")
        db_case.fallback_mode           = final_case.get("fallback_mode", False)
        db_case.failure_reason          = final_case.get("failure_reason")
        db_case.workflow_plan           = final_case.get("workflow_plan")
        db_case.trust_intelligence      = final_case.get("trust_intelligence")
        db_case.user_trust_score        = final_case.get("user_trust_score", 1.0)
        db_case.behavioral_risk_score   = final_case.get("behavioral_risk_score", 0.0)
        db_case.identity_status         = final_case.get("identity_status", "PENDING")
        db_case.fraud_reasoning_brief   = final_case.get("fraud_reasoning_brief")
        db_case.fraud_probability       = final_case.get("fraud_probability", 0.0)
        db_case.fraud_risk_level        = final_case.get("fraud_risk_level", "LOW")
        db_case.status                  = final_case.get("status", "Dispute Raised")
        db_case.workflow_ready          = True
        db_case.current_stage           = "completed"

    @staticmethod
    def _append_audit_log(
        db: Session,
        case_id: str,
        event_type: str,
        stage: str,
        message: str = "",
        actor: str = "system",
        payload: Optional[dict] = None,
    ) -> None:
        db.add(AuditLog(
            case_id=case_id, event_type=event_type, stage=stage,
            actor=actor, message=message, payload=payload or {},
        ))

    @staticmethod
    def _persist_workflow_states(db: Session, case_id: str, execution_trace: list) -> None:
        for entry in execution_trace:
            db.add(WorkflowState(
                case_id=case_id,
                node_name=entry.get("node", "unknown"),
                execution_time_ms=entry.get("duration_ms"),
                success=entry.get("success", True),
                error_message=entry.get("details") if not entry.get("success") else None,
            ))
