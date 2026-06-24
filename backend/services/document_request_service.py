"""Document request workflow — analyst requests documents, customer fulfills."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models import DocumentRequest, AuditLog, DisputeCase


def create_request(
    case_id: str,
    requested_by: str,
    document_type: str,
    description: str,
    due_date: Optional[datetime],
    db: Session,
    notify: bool = True,
    notify_docs: Optional[List[str]] = None,
) -> Optional[dict]:
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        return None

    # Block duplicate: same document_type already exists unfulfilled for this case
    existing = (
        db.query(DocumentRequest)
        .filter(
            DocumentRequest.case_id == case_id,
            DocumentRequest.document_type == document_type,
            DocumentRequest.fulfilled == False,
        )
        .first()
    )
    if existing:
        return existing.to_dict()

    dr = DocumentRequest(
        case_id=case_id,
        requested_by=requested_by,
        document_type=document_type,
        description=description,
        due_date=due_date,
    )
    db.add(dr)

    # Update case status
    case.status = "Pending Documents"
    case.updated_at = datetime.now(timezone.utc)

    log = AuditLog(
        case_id=case_id,
        event_type="DOCUMENT_REQUESTED",
        stage="analyst_action",
        actor=requested_by,
        message=f"Document requested: {document_type}",
        payload={"document_type": document_type, "description": description},
    )
    db.add(log)

    # STATUS_CHANGED log for customer timeline
    log2 = AuditLog(
        case_id=case_id,
        event_type="STATUS_CHANGED",
        stage="analyst_action",
        actor=requested_by,
        message="Status changed to Pending Documents",
        payload={"old_status": case.status, "new_status": "Pending Documents"},
    )
    db.add(log2)

    db.commit()
    db.refresh(dr)

    # Trigger email only when notify=True; use notify_docs list if provided
    if notify:
        try:
            from services.communication_service import trigger_communication_async
            docs_to_list = notify_docs or [
                r.document_type
                for r in db.query(DocumentRequest)
                .filter(DocumentRequest.case_id == case_id, DocumentRequest.fulfilled == False)
                .all()
            ]
            trigger_communication_async(
                case_id=case_id,
                notification_type="DOCUMENT_REQUESTED",
                context={"requested_documents": docs_to_list, "_skip_dedup": True},
            )
        except Exception:
            pass

    return dr.to_dict()


def fulfill_request(request_id: int, db: Session) -> Optional[dict]:
    dr = db.query(DocumentRequest).filter(DocumentRequest.id == request_id).first()
    if not dr or dr.fulfilled:
        return None
    dr.fulfilled = True
    dr.fulfilled_at = datetime.now(timezone.utc)

    log = AuditLog(
        case_id=dr.case_id,
        event_type="DOCUMENT_FULFILLED",
        stage="customer_action",
        actor="customer",
        message=f"Document request fulfilled: {dr.document_type}",
        payload={"request_id": request_id},
    )
    db.add(log)
    db.commit()
    db.refresh(dr)
    return dr.to_dict()


def get_requests(case_id: str, db: Session) -> List[dict]:
    return [
        r.to_dict()
        for r in db.query(DocumentRequest)
        .filter(DocumentRequest.case_id == case_id)
        .order_by(DocumentRequest.created_at)
        .all()
    ]

