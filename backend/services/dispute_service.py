"""
DisputeService — orchestrates workflow execution and database persistence.
Sits between the API layer and the LangGraph workflow / ORM layer.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from workflows.dispute_workflow import run_dispute_workflow
from database.models import DisputeCase, AuditLog, WorkflowState
from utils.logger import api_logger, audit_logger, log_workflow_event
from utils.helpers import utc_now_iso
from services.priority_engine import compute_priority
from services.sla_service import compute_sla_deadline
from services.queue_assignment_service import assign_queue
from services.duplicate_detection_service import find_duplicate
from services.manual_review_service import should_flag_manual_review


class DisputeService:

    # ── Submission ─────────────────────────────────────────────────────────────

    @staticmethod
    def submit_dispute(dispute_input: dict, db: Session) -> dict:
        """
        Full dispute submission pipeline:
          1. Run LangGraph workflow
          2. Persist dispute case
          3. Write audit log
          4. Persist workflow state snapshots
        Returns the persisted DisputeCase dict.
        """
        audit_logger.info(
            "Dispute submission received",
            extra={
                "customer_id": dispute_input.get("customer_id"),
                "transaction_id": dispute_input.get("transaction_id"),
            },
        )

        # Execute the LangGraph workflow
        workflow_result = run_dispute_workflow(dispute_input)
        final_case = workflow_result.get("final_case")
        validation_errors = workflow_result.get("validation_errors", [])
        execution_trace = workflow_result.get("execution_trace", [])

        if not final_case:
            # Validation failed — log and return error info
            audit_logger.warning(
                "Dispute rejected — validation failed",
                extra={"errors": validation_errors},
            )
            return {
                "success": False,
                "errors": validation_errors,
                "case_id": workflow_result.get("case_id", ""),
                "final_case": None,
            }

        # Enterprise enrichment before persisting
        priority_score, priority_label = compute_priority(final_case)
        final_case["priority"] = priority_label
        final_case["priority_score"] = priority_score

        queue = assign_queue(final_case)
        final_case["assigned_queue"] = queue

        sla_deadline = compute_sla_deadline(priority_label)
        final_case["sla_deadline"] = sla_deadline

        manual_flag, manual_reason = should_flag_manual_review(final_case)
        final_case["requires_manual_review"] = manual_flag
        final_case["manual_review_reason"] = manual_reason if manual_flag else None

        # Persist the dispute case
        db_case = DisputeService._persist_case(final_case, db)

        # Duplicate detection (post-persist so we exclude this case_id)
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

        if manual_flag:
            DisputeService._append_audit_log(
                db=db, case_id=db_case.case_id,
                event_type="MANUAL_REVIEW_FLAGGED", stage="post_analysis",
                message=manual_reason,
                payload={"reason": manual_reason},
            )

        # Append audit log
        DisputeService._append_audit_log(
            db=db,
            case_id=db_case.case_id,
            event_type="CASE_CREATED",
            stage="structured_output",
            message=f"Dispute case created. Category: {db_case.dispute_category}, Priority: {db_case.priority}",
            payload={
                "confidence_score": db_case.confidence_score,
                "risk_tags": db_case.risk_tags,
                "assigned_queue": queue,
                "priority_score": priority_score,
            },
        )

        # Persist workflow state snapshots
        DisputeService._persist_workflow_states(db, db_case.case_id, execution_trace)

        db.commit()

        audit_logger.info(
            "Dispute case persisted",
            extra={"case_id": db_case.case_id, "priority": db_case.priority},
        )

        return {
            "success": True,
            "errors": [],
            "case_id": db_case.case_id,
            "final_case": db_case.to_dict(),
        }

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
        total = db.query(DisputeCase).count()
        open_cases = db.query(DisputeCase).filter(
            DisputeCase.status.in_(["Dispute Raised", "Under Investigation", "Pending Documents"])
        ).count()
        fraud_cases = db.query(DisputeCase).filter(DisputeCase.fraud_suspicion == True).count()
        critical_cases = db.query(DisputeCase).filter(DisputeCase.priority == "CRITICAL").count()

        avg_conf = db.query(func.avg(DisputeCase.confidence_score)).scalar() or 0.0

        # Category breakdown
        cat_rows = db.query(DisputeCase.dispute_category, func.count()).group_by(DisputeCase.dispute_category).all()
        cases_by_category = {row[0]: row[1] for row in cat_rows if row[0]}

        # Priority breakdown
        pri_rows = db.query(DisputeCase.priority, func.count()).group_by(DisputeCase.priority).all()
        cases_by_priority = {row[0]: row[1] for row in pri_rows if row[0]}

        # Status breakdown
        stat_rows = db.query(DisputeCase.status, func.count()).group_by(DisputeCase.status).all()
        cases_by_status = {row[0]: row[1] for row in stat_rows if row[0]}

        recent = db.query(DisputeCase).order_by(desc(DisputeCase.created_at)).limit(5).all()

        return {
            "total_cases": total,
            "open_cases": open_cases,
            "fraud_cases": fraud_cases,
            "critical_cases": critical_cases,
            "avg_confidence_score": round(float(avg_conf), 3),
            "cases_by_category": cases_by_category,
            "cases_by_priority": cases_by_priority,
            "cases_by_status": cases_by_status,
            "recent_cases": [c.to_dict() for c in recent],
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

        old_status = case.status
        case.status = new_status
        case.updated_at = datetime.now(timezone.utc)

        DisputeService._append_audit_log(
            db=db,
            case_id=case_id,
            event_type="STATUS_CHANGED",
            stage="manual_update",
            actor=actor,
            message=f"Status changed from '{old_status}' to '{new_status}'",
            payload={"note": note, "actor": actor},
        )
        db.commit()
        db.refresh(case)
        return case.to_dict()

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _persist_case(final_case: dict, db: Session) -> DisputeCase:
        db_case = DisputeCase(
            case_id=final_case["case_id"],
            customer_id=final_case.get("customer_id", ""),
            customer_name=final_case.get("customer_name", ""),
            email=final_case.get("email", ""),
            phone=final_case.get("phone", ""),
            transaction_id=final_case.get("transaction_id", ""),
            transaction_type=final_case.get("transaction_type", ""),
            merchant=final_case.get("merchant", ""),
            amount=final_case.get("amount", 0),
            currency=final_case.get("currency", "INR"),
            transaction_date=final_case.get("transaction_date", ""),
            transaction_time=final_case.get("transaction_time", ""),
            customer_comment=final_case.get("customer_comment", ""),
            dispute_reason=final_case.get("dispute_reason", ""),
            fraud_selected=final_case.get("fraud_selected", False),
            dispute_category=final_case.get("dispute_category", "Other"),
            fraud_suspicion=final_case.get("fraud_suspicion", False),
            customer_intent_summary=final_case.get("customer_intent_summary", ""),
            priority=final_case.get("priority", "MEDIUM"),
            confidence_score=final_case.get("confidence_score", 0.5),
            risk_tags=final_case.get("risk_tags", []),
            structured_reasoning=final_case.get("structured_reasoning", ""),
            status="Dispute Raised",
            workflow_ready=True,
            # Enterprise fields
            assigned_queue=final_case.get("assigned_queue"),
            priority_score=final_case.get("priority_score", 0.0),
            sla_deadline=final_case.get("sla_deadline"),
            sla_breached=False,
            requires_manual_review=final_case.get("requires_manual_review", False),
            manual_review_reason=final_case.get("manual_review_reason"),
        )
        db.add(db_case)
        db.flush()  # Get PK without committing
        return db_case

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
        log = AuditLog(
            case_id=case_id,
            event_type=event_type,
            stage=stage,
            actor=actor,
            message=message,
            payload=payload or {},
        )
        db.add(log)

    @staticmethod
    def _persist_workflow_states(db: Session, case_id: str, execution_trace: list) -> None:
        for entry in execution_trace:
            ws = WorkflowState(
                case_id=case_id,
                node_name=entry.get("node", "unknown"),
                execution_time_ms=entry.get("duration_ms"),
                success=entry.get("success", True),
                error_message=entry.get("details") if not entry.get("success") else None,
            )
            db.add(ws)
