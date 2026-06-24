"""
Analyst action handler.

Actions: approve, reject, escalate, reassign, request_docs, add_note, mark_sla_breach
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DisputeCase, AuditLog


_ACTION_STATUS_MAP = {
    "approve":  "Resolved",
    "reject":   "Rejected",
    "escalate": "Escalated",
}


def perform_action(
    case_id: str,
    action: str,          # approve | reject | escalate | reassign | mark_sla_breach
    analyst: str,
    db: Session,
    note: str = "",
    new_assignee: str = "",
    new_queue: str = "",
) -> Optional[dict]:
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        return None

    now = datetime.now(timezone.utc)
    old_status = case.status

    if action in _ACTION_STATUS_MAP:
        new_status = _ACTION_STATUS_MAP[action]
        case.status = new_status
        case.updated_at = now
        _audit(db, case_id, "STATUS_CHANGED", analyst,
               f"Status changed to {new_status} via analyst action '{action}'",
               {"old_status": old_status, "new_status": new_status, "note": note, "action": action})

    elif action == "reassign":
        if new_assignee:
            case.assigned_analyst = new_assignee
        if new_queue:
            case.assigned_queue = new_queue
        case.updated_at = now
        _audit(db, case_id, "CASE_REASSIGNED", analyst,
               f"Case reassigned to {new_assignee or 'unassigned'} / queue {new_queue or 'unchanged'}",
               {"new_assignee": new_assignee, "new_queue": new_queue, "note": note})

    elif action == "mark_sla_breach":
        case.sla_breached = True
        case.updated_at = now
        _audit(db, case_id, "SLA_BREACHED", analyst,
               f"SLA manually marked as breached by {analyst}",
               {"note": note})

    elif action == "under_investigation":
        case.status = "Under Investigation"
        case.updated_at = now
        _audit(db, case_id, "STATUS_CHANGED", analyst,
               "Status changed to Under Investigation",
               {"old_status": old_status, "new_status": "Under Investigation", "action": action})

    db.commit()
    db.refresh(case)

    # Trigger CCA communication for status update
    if action in _ACTION_STATUS_MAP or action == "under_investigation":
        try:
            from services.communication_service import trigger_communication_async
            _STATUS_COMM_MAP = {
                "Under Investigation": "INVESTIGATION_STARTED",
                "Pending Documents":   "DOCUMENT_REQUESTED",
                "Resolved":            "CASE_RESOLVED",
                "Rejected":            "CASE_RESOLVED",
                "Closed":              "CASE_RESOLVED",
            }
            comm_type = _STATUS_COMM_MAP.get(case.status, "STATUS_CHANGED")
            context = {"new_status": case.status, "resolution_status": case.status}
            if note:
                context["resolution_summary"] = note
            trigger_communication_async(case_id, comm_type, context=context)
        except Exception:
            pass

    return case.to_dict()


def _audit(db, case_id, event_type, actor, message, payload):
    db.add(AuditLog(
        case_id=case_id,
        event_type=event_type,
        stage="analyst_action",
        actor=actor,
        message=message,
        payload=payload,
    ))

