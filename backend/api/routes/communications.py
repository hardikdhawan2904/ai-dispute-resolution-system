"""
Communications API — read and trigger customer notifications.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import CommunicationLog, DisputeCase
from services.communication_service import trigger_communication

router = APIRouter(prefix="/api/communications", tags=["Communications"])


class SendCommunicationRequest(BaseModel):
    notification_type: str
    context: Optional[dict] = None


@router.get("/{case_id}")
def get_case_communications(case_id: str, db: Session = Depends(get_db)):
    """Return all communication logs for a case, newest first."""
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    logs = (
        db.query(CommunicationLog)
        .filter(CommunicationLog.case_id == case_id)
        .order_by(CommunicationLog.created_at.desc())
        .all()
    )
    return {
        "case_id":        case_id,
        "total":          len(logs),
        "communications": [log.to_dict() for log in logs],
    }


@router.post("/{case_id}/send")
def send_communication(
    case_id: str,
    payload: SendCommunicationRequest,
    db: Session = Depends(get_db),
):
    """Manually trigger a communication for a case (ops analyst action)."""
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    ctx = dict(payload.context or {})
    ctx["_skip_dedup"] = True   # manual sends always go through

    result = trigger_communication(
        case_id           = case_id,
        notification_type = payload.notification_type,
        db                = db,
        context           = ctx,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to trigger communication")

    return {
        "case_id": case_id,
        "result":  result,
    }

