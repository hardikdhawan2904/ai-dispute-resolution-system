"""
Full investigation timeline — merges system events, analyst actions, and customer events.

Returns chronological list of timeline entries with actor and display metadata.
"""
from datetime import timezone
from typing import List

from sqlalchemy.orm import Session

from database.models import AuditLog, CaseNote, DocumentRequest

_EVENT_DISPLAY = {
    "CASE_CREATED":          {"label": "Case Created",             "color": "blue",   "icon": "FileText"},
    "STATUS_CHANGED":        {"label": "Status Updated",           "color": "indigo", "icon": "RefreshCw"},
    "DOCUMENT_REQUESTED":    {"label": "Documents Requested",      "color": "amber",  "icon": "FileSearch"},
    "DOCUMENT_UPLOADED":     {"label": "Documents Uploaded",       "color": "green",  "icon": "Upload"},
    "DOCUMENT_FULFILLED":    {"label": "Document Request Fulfilled","color": "green",  "icon": "CheckCircle"},
    "NOTE_ADDED":            {"label": "Note Added",               "color": "gray",   "icon": "MessageSquare"},
    "CASE_REASSIGNED":       {"label": "Case Reassigned",          "color": "purple", "icon": "Users"},
    "SLA_BREACHED":          {"label": "SLA Breach",               "color": "red",    "icon": "AlertTriangle"},
    "WORKFLOW_START":        {"label": "AI Analysis Started",      "color": "blue",   "icon": "Cpu"},
    "ANALYSIS_COMPLETE":     {"label": "Analysis Complete",        "color": "green",  "icon": "CheckSquare"},
    "DUPLICATE_DETECTED":    {"label": "Duplicate Detected",       "color": "orange", "icon": "Copy"},
    "MANUAL_REVIEW_FLAGGED": {"label": "Flagged for Manual Review","color": "red",    "icon": "Flag"},
    "LOCK_ACQUIRED":         {"label": "Case Locked",              "color": "gray",   "icon": "Lock"},
    "LOCK_RELEASED":         {"label": "Case Unlocked",            "color": "gray",   "icon": "Unlock"},
}


def _iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build_timeline(case_id: str, db: Session) -> List[dict]:
    """Return chronologically sorted timeline entries for a case."""
    entries = []

    # Audit logs
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at)
        .all()
    )
    for log in logs:
        meta = _EVENT_DISPLAY.get(log.event_type, {"label": log.event_type, "color": "gray", "icon": "Info"})
        entries.append({
            "id": f"log-{log.id}",
            "type": log.event_type,
            "label": meta["label"],
            "color": meta["color"],
            "icon": meta["icon"],
            "actor": log.actor or "system",
            "actor_type": _actor_type(log.actor),
            "message": log.message or "",
            "payload": log.payload or {},
            "timestamp": _iso(log.created_at),
            "source": "audit",
        })

    # Sort chronologically
    entries.sort(key=lambda e: e["timestamp"] or "")
    return entries


def _actor_type(actor: str | None) -> str:
    if not actor:
        return "system"
    if actor == "customer":
        return "customer"
    if actor in ("system", "ai", "workflow"):
        return "system"
    return "analyst"
