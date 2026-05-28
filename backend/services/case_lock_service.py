"""
Pessimistic case locking (30-minute TTL).

Prevents two analysts from updating the same case simultaneously.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DisputeCase

_LOCK_TTL_MINUTES = 30


def acquire_lock(case_id: str, analyst: str, db: Session) -> dict:
    """
    Attempts to acquire the lock for analyst.
    Returns {"acquired": bool, "locked_by": str, "locked_at": str, "expires_at": str}
    """
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        return {"acquired": False, "error": "Case not found"}

    now = datetime.now(timezone.utc)

    # Check if an unexpired lock is held by someone else
    if case.locked_by and case.locked_by != analyst:
        locked_at = case.locked_at
        if locked_at and locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        if locked_at and (now - locked_at) < timedelta(minutes=_LOCK_TTL_MINUTES):
            expires_at = locked_at + timedelta(minutes=_LOCK_TTL_MINUTES)
            return {
                "acquired": False,
                "locked_by": case.locked_by,
                "locked_at": locked_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }

    case.locked_by = analyst
    case.locked_at = now
    db.commit()

    return {
        "acquired": True,
        "locked_by": analyst,
        "locked_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=_LOCK_TTL_MINUTES)).isoformat(),
    }


def release_lock(case_id: str, analyst: str, db: Session) -> bool:
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        return False
    if case.locked_by == analyst:
        case.locked_by = None
        case.locked_at = None
        db.commit()
        return True
    return False


def check_lock(case_id: str, db: Session) -> dict:
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case or not case.locked_by:
        return {"locked": False}

    now = datetime.now(timezone.utc)
    locked_at = case.locked_at
    if locked_at and locked_at.tzinfo is None:
        locked_at = locked_at.replace(tzinfo=timezone.utc)

    if locked_at and (now - locked_at) >= timedelta(minutes=_LOCK_TTL_MINUTES):
        # Lock has expired
        return {"locked": False}

    expires_at = locked_at + timedelta(minutes=_LOCK_TTL_MINUTES) if locked_at else None
    return {
        "locked": True,
        "locked_by": case.locked_by,
        "locked_at": locked_at.isoformat() if locked_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
