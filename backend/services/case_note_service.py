"""Case note creation and retrieval."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models import CaseNote, AuditLog, DisputeCase


def add_note(
    case_id: str,
    analyst: str,
    note: str,
    is_internal: bool,
    db: Session,
) -> Optional[dict]:
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        return None

    cn = CaseNote(
        case_id=case_id,
        analyst=analyst,
        note=note,
        is_internal=is_internal,
    )
    db.add(cn)

    log = AuditLog(
        case_id=case_id,
        event_type="NOTE_ADDED",
        stage="analyst_action",
        actor=analyst,
        message=f"{'Internal' if is_internal else 'Customer-visible'} note added by {analyst}",
        payload={"note_preview": note[:120], "is_internal": is_internal},
    )
    db.add(log)
    db.commit()
    db.refresh(cn)
    return cn.to_dict()


def get_notes(case_id: str, db: Session, include_internal: bool = True) -> List[dict]:
    q = db.query(CaseNote).filter(CaseNote.case_id == case_id)
    if not include_internal:
        q = q.filter(CaseNote.is_internal == False)
    return [n.to_dict() for n in q.order_by(CaseNote.created_at).all()]

