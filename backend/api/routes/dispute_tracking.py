"""
Public dispute tracking endpoints — no authentication required.

Returns ONLY customer-safe status information derived from the dispute record
and its audit log. Internal AI analysis, fraud signals, confidence scores,
risk tags, LangGraph workflow states, and investigation details are NEVER exposed.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database.database import get_db, SessionLocal
from database.models import DisputeCase, AuditLog
from schemas.customer_tracking import (
    CustomerTrackingResponse,
    build_tracking_response,
    CUSTOMER_STATUS_MAP,
)
from utils.logger import api_logger

router = APIRouter(prefix="/api/disputes", tags=["Dispute Tracking"])

_TERMINAL_STATUSES = {"Resolved", "Rejected", "Closed"}
_SSE_POLL_INTERVAL  = 15    # seconds between DB polls
_SSE_MAX_TICKS      = 120   # 120 × 15 s = 30 minutes max stream lifetime


# ── REST tracking endpoint ─────────────────────────────────────────────────────

@router.get("/track/{case_id}", response_model=CustomerTrackingResponse)
def track_dispute(case_id: str, db: Session = Depends(get_db)):
    """
    Public endpoint — customer looks up a dispute by case reference.
    Returns only safe status, timeline, and case summary.
    """
    case = (
        db.query(DisputeCase)
        .filter(DisputeCase.case_id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found. Please check your case reference and try again.",
        )

    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )

    return build_tracking_response(case, audit_logs)


# ── SSE streaming endpoint ─────────────────────────────────────────────────────

@router.get("/track/{case_id}/events")
async def stream_dispute_events(case_id: str):
    """
    SSE stream — pushes customer-safe status updates whenever the internal
    dispute status changes. Polls the database every 15 seconds.
    Stream closes automatically after 30 minutes or when the case is resolved.
    """

    async def event_generator():
        last_status: str | None = None
        idle_ticks = 0

        # Verify case exists before opening the stream
        db = SessionLocal()
        try:
            exists = (
                db.query(DisputeCase.case_id)
                .filter(DisputeCase.case_id == case_id)
                .first()
            )
        finally:
            db.close()

        if not exists:
            yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
            return

        while idle_ticks < _SSE_MAX_TICKS:
            db = SessionLocal()
            try:
                case = (
                    db.query(DisputeCase)
                    .filter(DisputeCase.case_id == case_id)
                    .first()
                )
                if not case:
                    yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                    return

                current_status = CUSTOMER_STATUS_MAP.get(case.status, "Under Review")

                if current_status != last_status:
                    last_status = current_status
                    idle_ticks  = 0

                    audit_logs = (
                        db.query(AuditLog)
                        .filter(AuditLog.case_id == case_id)
                        .order_by(AuditLog.created_at.asc())
                        .all()
                    )
                    payload = build_tracking_response(case, audit_logs)
                    yield f"data: {json.dumps(payload)}\n\n"

                    if case.status in _TERMINAL_STATUSES:
                        return
                else:
                    idle_ticks += 1
                    # keepalive comment — prevents proxy timeouts, not visible to client
                    yield ": keepalive\n\n"

            except Exception as exc:
                api_logger.error(f"SSE error tracking {case_id}: {exc}")
                yield ": error\n\n"
            finally:
                db.close()

            await asyncio.sleep(_SSE_POLL_INTERVAL)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
