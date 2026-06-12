"""
Pydantic schemas for request/response validation.
All schemas follow strict BFSI data standards.
"""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


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


# ── Request Schemas ───────────────────────────────────────────────────────────

class DisputeSubmissionRequest(BaseModel):
    """Intake form payload from the banking portal."""

    # customer_name, email, phone are optional here — the backend always overwrites
    # them from BankCustomer so the DB is the single source of truth.
    customer_id: str = Field(..., min_length=4, max_length=64, description="Bank customer identifier")
    customer_name: Optional[str] = Field(default=None, max_length=256, description="Ignored — filled from DB")
    email: Optional[str] = Field(default=None, description="Ignored — filled from DB")
    phone: Optional[str] = Field(default=None, description="Ignored — filled from DB")

    transaction_id: str = Field(..., min_length=4, max_length=128, description="Bank transaction reference")
    # Fields below are ignored from form — backend always overwrites from transactions table.
    transaction_type: Optional[str]  = Field(default=None, description="Ignored — filled from DB")
    merchant:         Optional[str]  = Field(default=None, max_length=256, description="Ignored — filled from DB")
    amount:           Optional[float] = Field(default=None, description="Ignored — filled from DB")
    currency:         str = Field(default="INR", max_length=8, description="ISO 4217 currency code")
    transaction_date: Optional[str]  = Field(default=None, description="Ignored — filled from DB")
    transaction_time: Optional[str]  = Field(default=None, description="Ignored — filled from DB")

    customer_comment: str = Field(..., min_length=10, max_length=2000, description="Customer's free-text complaint")
    dispute_reason: str = Field(..., min_length=5, max_length=512, description="Primary dispute reason")
    fraud_selected: bool = Field(default=False, description="Customer checked the 'Fraud' option")
    transaction_metadata: Optional[dict] = Field(default=None, description="Type-specific transaction metadata (card digits, UTR, UPI ID, etc.)")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v <= 0 or v > 100_000_000:
            raise ValueError("Amount must be between 0 and 100,000,000")
        return round(v, 2)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and "@" not in v:
            raise ValueError("Invalid email format")
        return v



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
    evidence_match: Optional[bool] = None
    evidence_match_note: Optional[str] = None
    confidence_factors: List[str] = []
    tools_used: List[str] = []
    agent_metadata: Optional[dict] = None
    metrics: Optional[dict] = None
    fallback_mode: bool = False
    failure_reason: Optional[str] = None
    status: str
    workflow_ready: bool
    # Enterprise fields
    assigned_queue: Optional[str] = None
    assigned_analyst: Optional[str] = None
    priority_score: float = 0.0
    sla_deadline: Optional[str] = None
    sla_breached: bool = False
    sla_paused_at: Optional[str] = None
    duplicate_of: Optional[str] = None
    requires_manual_review: bool = False
    manual_review_reason: Optional[str] = None
    locked_by: Optional[str] = None
    locked_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str]
    investigation_plan: Optional[dict] = None
    workflow_plan: Optional[dict] = None
    # Trust & Identity Agent
    trust_intelligence: Optional[dict] = None
    user_trust_score: float = 1.0
    behavioral_risk_score: float = 0.0
    identity_status: str = "PENDING"
    # Fraud Reasoning Agent
    fraud_reasoning_brief: Optional[dict] = None
    fraud_probability: float = 0.0
    fraud_risk_level: str = "LOW"
    # Evidence Intelligence Agent
    evidence_assessment: Optional[dict] = None

    model_config = {"from_attributes": True}


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
