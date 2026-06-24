"""
Customer-safe response schemas — strips all internal AI intelligence.
Customers NEVER see: confidence scores, fraud signals, risk tags, AI reasoning, workflow states.
"""
from typing import Optional
from pydantic import BaseModel


CUSTOMER_STATUS_MAP = {
    "Dispute Raised":      "Dispute Submitted",
    "Under Investigation": "Under Review",
    "Pending Documents":   "Documents Requested",
    "Escalated":           "Investigation In Progress",
    "Resolved":            "Resolved",
    "Rejected":            "Resolved",
    "Closed":              "Resolved",
}


class CustomerDisputeResponse(BaseModel):
    """Dispute data safe to expose to authenticated customers."""
    case_id: str
    transaction_id: str
    transaction_type: str
    merchant: str
    amount: float
    currency: str
    transaction_date: Optional[str]
    status: str           # mapped to customer-friendly label
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class CustomerDisputeSubmissionResponse(BaseModel):
    success: bool
    case_id: str
    message: str
    dispute_case: CustomerDisputeResponse


def to_customer_response(case: dict) -> CustomerDisputeResponse:
    raw_status = case.get("status", "Dispute Raised")
    friendly_status = CUSTOMER_STATUS_MAP.get(raw_status, "Under Review")
    return CustomerDisputeResponse(
        case_id=case.get("case_id", ""),
        transaction_id=case.get("transaction_id", ""),
        transaction_type=case.get("transaction_type", ""),
        merchant=case.get("merchant", ""),
        amount=case.get("amount", 0.0),
        currency=case.get("currency", "INR"),
        transaction_date=case.get("transaction_date"),
        status=friendly_status,
        created_at=case.get("created_at") or "",
        updated_at=case.get("updated_at"),
    )

