"""
Pydantic schemas for request/response validation.
All schemas follow strict BFSI data standards.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# ── Enumerations ──────────────────────────────────────────────────────────────

DisputeCategory = Literal[
    "Unauthorized Transaction",
    "Duplicate Transaction",
    "Refund Not Received",
    "Product Not Received",
    "Subscription Abuse",
    "ATM Cash Issue",
    "Merchant Dispute",
    "Friendly Fraud",
    "Other",
]

TransactionType = Literal[
    "Credit Card",
    "Debit Card",
    "UPI",
    "Net Banking",
    "Wallet",
    "POS",
    "ATM",
    "Online Purchase",
    "International",
]

Priority = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

CaseStatus = Literal[
    "Dispute Raised",
    "Under Investigation",
    "Pending Documents",
    "Escalated",
    "Resolved",
    "Rejected",
    "Closed",
]

RiskTag = Literal[
    "HIGH_VALUE_TRANSACTION",
    "INTERNATIONAL_TRANSACTION",
    "POSSIBLE_FRAUD",
    "DUPLICATE_PAYMENT",
    "FRIENDLY_FRAUD_RISK",
    "HIGH_PRIORITY_CASE",
    "OTP_VERIFIED",
    "DEVICE_MISMATCH",
    "SUSPICIOUS_BEHAVIOR",
    "CARD_NOT_PRESENT",
    "RECURRING_DISPUTE",
    "MERCHANT_BLACKLISTED",
    "VELOCITY_BREACH",
]


# ── Request Schemas ───────────────────────────────────────────────────────────

class DisputeSubmissionRequest(BaseModel):
    """Intake form payload from the banking portal."""

    customer_name: str = Field(..., min_length=2, max_length=256, description="Full name of the customer")
    customer_id: str = Field(..., min_length=4, max_length=64, description="Bank customer identifier")
    email: str = Field(..., description="Customer email address")
    phone: str = Field(default="", description="Customer phone number")

    transaction_id: str = Field(..., min_length=4, max_length=128, description="Bank transaction reference")
    transaction_type: TransactionType = Field(..., description="Type of the disputed transaction")
    merchant: str = Field(..., min_length=1, max_length=256, description="Merchant or payee name")
    amount: float = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(default="INR", max_length=8, description="ISO 4217 currency code")
    transaction_date: str = Field(..., description="Date of the transaction (YYYY-MM-DD)")
    transaction_time: str = Field(default="", description="Time of transaction (HH:MM)")

    customer_comment: str = Field(..., min_length=10, max_length=2000, description="Customer's free-text complaint")
    dispute_reason: str = Field(..., min_length=5, max_length=512, description="Primary dispute reason")
    fraud_selected: bool = Field(default=False, description="Customer checked the 'Fraud' option")
    transaction_metadata: Optional[dict] = Field(default=None, description="Type-specific transaction metadata (card digits, UTR, UPI ID, etc.)")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0 or v > 100_000_000:
            raise ValueError("Amount must be between 0 and 100,000,000")
        return round(v, 2)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper().strip()


# ── AI Output Schema (LangGraph structured output) ────────────────────────────

class DisputeCaseOutput(BaseModel):
    """The structured JSON produced by the Dispute Understanding Agent."""

    case_id: str
    customer_id: str
    transaction_id: str
    transaction_type: str
    merchant: str
    amount: float
    currency: str
    dispute_category: str
    fraud_suspicion: bool
    customer_intent_summary: str
    priority: Priority
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    risk_tags: List[str] = Field(default_factory=list)
    structured_reasoning: str
    status: str = "Dispute Raised"
    workflow_ready: bool = True
    created_at: str

    @field_validator("confidence_score")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ── Response Schemas ──────────────────────────────────────────────────────────

class DisputeCaseResponse(BaseModel):
    """Full case response returned to the frontend."""
    case_id: str
    customer_id: str
    customer_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    transaction_id: str
    transaction_type: str
    merchant: str
    amount: float
    currency: str
    transaction_date: Optional[str]
    transaction_time: Optional[str]
    customer_comment: Optional[str]
    dispute_reason: Optional[str]
    fraud_selected: bool
    dispute_category: Optional[str]
    fraud_suspicion: bool
    customer_intent_summary: Optional[str]
    priority: str
    confidence_score: float
    risk_tags: List[str]
    structured_reasoning: Optional[str]
    status: str
    workflow_ready: bool
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class DisputeSubmissionResponse(BaseModel):
    """Returned immediately after successful dispute submission."""
    success: bool
    case_id: str
    message: str
    dispute_case: DisputeCaseResponse


class CasesListResponse(BaseModel):
    total: int
    cases: List[DisputeCaseResponse]


class DashboardStatsResponse(BaseModel):
    total_cases: int
    open_cases: int
    fraud_cases: int
    critical_cases: int
    avg_confidence_score: float
    cases_by_category: dict
    cases_by_priority: dict
    cases_by_status: dict
    recent_cases: List[DisputeCaseResponse]


class WorkflowStateResponse(BaseModel):
    case_id: str
    node_name: str
    execution_time_ms: Optional[float]
    success: bool
    error_message: Optional[str]
    created_at: str


class AuditLogResponse(BaseModel):
    id: int
    case_id: str
    event_type: str
    stage: Optional[str]
    actor: str
    message: Optional[str]
    created_at: str


class StatusUpdateRequest(BaseModel):
    status: CaseStatus
    actor: str = "operations_team"
    note: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    llm_provider: str
    llm_model: str
