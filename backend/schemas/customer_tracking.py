"""
Customer-safe tracking schemas for the public dispute tracking endpoint.

NEVER expose: AI reasoning, fraud signals, confidence scores, risk tags,
workflow states, LangGraph nodes, or any internal investigation details.
"""
from typing import List, Optional
from pydantic import BaseModel

from database.models import DisputeCase, AuditLog


# ── Status mapping — internal → customer-visible ───────────────────────────────

CUSTOMER_STATUS_MAP: dict[str, str] = {
    "Dispute Raised":      "Dispute Submitted",
    "Under Investigation": "Under Review",
    "Pending Documents":   "Documents Requested",
    "Escalated":           "Investigation In Progress",
    "Resolved":            "Resolved",
    "Rejected":            "Resolved",
    "Closed":              "Resolved",
}

_ESTIMATED_RESOLUTION: dict[str, str] = {
    "Dispute Raised":      "Within 7 business days",
    "Under Investigation": "Within 5 business days",
    "Pending Documents":   "Within 5 business days of document receipt",
    "Escalated":           "Within 3 business days",
    "Resolved":            "Resolved",
    "Rejected":            "Resolved",
    "Closed":              "Closed",
}

# Audit log STATUS_CHANGED → customer-visible description
_STATUS_CHANGE_MESSAGES: dict[str, str] = {
    "Under Investigation": "Case assigned to our disputes team for review",
    "Pending Documents":   "Additional documentation has been requested",
    "Escalated":           "Case under priority investigation",
    "Resolved":            "Investigation complete — resolution has been determined",
    "Rejected":            "Case review complete",
    "Closed":              "Case closed",
}

# Audit log event_type values that surface customer-visible timeline entries
_SURFACE_EVENTS = {"CASE_CREATED", "STATUS_CHANGED"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    description: str
    timestamp: Optional[str] = None


class CustomerTrackingResponse(BaseModel):
    case_id:              str
    status:               str           # customer-friendly label
    dispute_reason:       Optional[str] = None
    merchant:             str
    amount:               float
    currency:             str
    transaction_type:     str
    submission_date:      str
    last_updated:         Optional[str] = None
    estimated_resolution: str
    document_requested:   bool
    timeline:             List[TimelineEvent]


# ── Builder ────────────────────────────────────────────────────────────────────

def build_tracking_response(
    case: DisputeCase,
    audit_logs: List[AuditLog],
) -> dict:
    """
    Build a customer-safe tracking payload from a DisputeCase and its audit logs.
    Filters out all internal workflow events; only surfaces customer-visible milestones.
    """
    customer_status = CUSTOMER_STATUS_MAP.get(case.status, "Under Review")
    est_resolution  = _ESTIMATED_RESOLUTION.get(case.status, "Under review")
    doc_requested   = case.status == "Pending Documents"

    timeline: List[TimelineEvent] = []

    for log in audit_logs:
        event_type = (log.event_type or "").strip()

        if event_type not in _SURFACE_EVENTS:
            continue

        if event_type == "CASE_CREATED":
            timeline.append(TimelineEvent(
                description="Dispute received — case reference assigned",
                timestamp=log.created_at.isoformat() if log.created_at else None,
            ))

        elif event_type == "STATUS_CHANGED":
            payload    = log.payload or {}
            new_status = payload.get("new_status", "")
            msg        = _STATUS_CHANGE_MESSAGES.get(new_status)
            if msg:
                timeline.append(TimelineEvent(
                    description=msg,
                    timestamp=log.created_at.isoformat() if log.created_at else None,
                ))

    return CustomerTrackingResponse(
        case_id              = case.case_id,
        status               = customer_status,
        dispute_reason       = case.dispute_reason,
        merchant             = case.merchant or "",
        amount               = case.amount,
        currency             = case.currency or "INR",
        transaction_type     = case.transaction_type,
        submission_date      = case.created_at.isoformat() if case.created_at else "",
        last_updated         = case.updated_at.isoformat() if case.updated_at else None,
        estimated_resolution = est_resolution,
        document_requested   = doc_requested,
        timeline             = timeline,
    ).model_dump()
