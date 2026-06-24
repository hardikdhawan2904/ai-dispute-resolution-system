"""
SQLAlchemy ORM models for the BFSI Dispute Resolution Platform.

Tables:
  - bank_customers     : Bank customer profiles
  - merchant_profiles  : Merchant risk and complaint data
  - transactions       : All customer transactions
  - dispute_history    : Historical resolved dispute records
  - dispute_cases      : Core dispute case with AI analysis results
  - audit_logs         : Immutable audit trail for every workflow action
  - workflow_states    : Per-case workflow execution snapshots
  - case_notes         : Analyst notes attached to a case
  - document_requests  : Formal document requests sent to customers
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Boolean, Text, DateTime, Date,
    Integer, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship

# pyrefly: ignore [missing-import]
from database.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(dt) -> str | None:
    """Return ISO-8601 with +00:00 so JavaScript converts to browser local time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ── Bank Customers ────────────────────────────────────────────────────────────

class BankCustomer(Base):
    __tablename__ = "bank_customers"

    customer_id   = Column(String(64), primary_key=True, index=True)
    full_name     = Column(String(256), nullable=False)
    email         = Column(String(256), nullable=False)
    phone         = Column(String(32), nullable=False)
    joining_date  = Column(Date, nullable=True)

    def to_dict(self) -> dict:
        return {
            "customer_id":  self.customer_id,
            "full_name":    self.full_name,
            "email":        self.email,
            "phone":        self.phone,
            "joining_date": str(self.joining_date) if self.joining_date else None,
        }


# ── Merchant Profiles ─────────────────────────────────────────────────────────

class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    merchant_id               = Column(String(64), primary_key=True, index=True)
    merchant_name             = Column(String(256), nullable=False, index=True)
    merchant_category         = Column(String(128), nullable=False)
    total_transactions        = Column(Integer, default=0)
    total_disputes            = Column(Integer, default=0)
    fraud_complaints          = Column(Integer, default=0)
    resolved_customer_favor   = Column(Integer, default=0)
    resolved_merchant_favor   = Column(Integer, default=0)
    risk_level                = Column(String(32), default="LOW")  # LOW/MEDIUM/HIGH/CRITICAL
    blacklisted               = Column(Boolean, default=False)
    created_at                = Column(DateTime, default=_utc_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "merchant_id":             self.merchant_id,
            "merchant_name":           self.merchant_name,
            "merchant_category":       self.merchant_category,
            "total_transactions":      self.total_transactions,
            "total_disputes":          self.total_disputes,
            "fraud_complaints":        self.fraud_complaints,
            "resolved_customer_favor": self.resolved_customer_favor,
            "resolved_merchant_favor": self.resolved_merchant_favor,
            "risk_level":              self.risk_level,
            "blacklisted":             self.blacklisted,
            "created_at":              _iso(self.created_at),
        }


# ── Transactions ──────────────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id    = Column(String(64), primary_key=True, index=True)
    customer_id       = Column(String(64), index=True, nullable=False)
    merchant_id       = Column(String(64), nullable=True)
    merchant_name     = Column(String(256), nullable=False)
    amount            = Column(Float, nullable=False)
    currency          = Column(String(8), default="INR")
    transaction_type  = Column(String(64), nullable=False)   # UPI/NEFT/IMPS/Debit Card/etc.
    transaction_date  = Column(DateTime, nullable=False)
    status            = Column(String(32), default="Success")  # Success/Failed/Pending/Reversed
    location          = Column(String(128), nullable=True)
    latitude          = Column(Float, nullable=True)   # GPS coordinates for accurate geovelocity
    longitude         = Column(Float, nullable=True)
    device_id         = Column(String(64), nullable=True)
    is_disputed       = Column(Boolean, default=False)
    created_at        = Column(DateTime, default=_utc_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "transaction_id":   self.transaction_id,
            "customer_id":      self.customer_id,
            "merchant_id":      self.merchant_id,
            "merchant_name":    self.merchant_name,
            "amount":           self.amount,
            "currency":         self.currency,
            "transaction_type": self.transaction_type,
            "transaction_date": _iso(self.transaction_date),
            "status":           self.status,
            "location":         self.location,
            "latitude":         self.latitude,
            "longitude":        self.longitude,
            "device_id":        self.device_id,
            "is_disputed":      self.is_disputed,
            "created_at":       _iso(self.created_at),
        }


# ── Dispute History ───────────────────────────────────────────────────────────

class DisputeHistory(Base):
    """Historical (resolved) dispute records — pre-populated reference data."""
    __tablename__ = "dispute_history"

    id                    = Column(Integer, primary_key=True, index=True)
    case_id               = Column(String(64), unique=True, index=True, nullable=False)
    customer_id           = Column(String(64), index=True, nullable=False)
    merchant_id           = Column(String(64), nullable=True)
    transaction_id        = Column(String(64), nullable=True)
    dispute_category      = Column(String(128), nullable=False)
    fraud_claim           = Column(Boolean, default=False)
    amount                = Column(Float, nullable=False)
    resolution            = Column(Text, nullable=True)
    resolved_in_favor_of  = Column(String(32), nullable=True)  # customer/merchant/partial
    resolution_days       = Column(Integer, nullable=True)
    status                = Column(String(32), default="Resolved")  # Resolved/Rejected/Closed
    created_at            = Column(DateTime, nullable=False)
    resolved_at           = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":                    self.id,
            "case_id":               self.case_id,
            "customer_id":           self.customer_id,
            "merchant_id":           self.merchant_id,
            "transaction_id":        self.transaction_id,
            "dispute_category":      self.dispute_category,
            "fraud_claim":           self.fraud_claim,
            "amount":                self.amount,
            "resolution":            self.resolution,
            "resolved_in_favor_of":  self.resolved_in_favor_of,
            "resolution_days":       self.resolution_days,
            "status":                self.status,
            "created_at":            _iso(self.created_at),
            "resolved_at":           _iso(self.resolved_at),
        }


# ── Dispute Cases ─────────────────────────────────────────────────────────────

class DisputeCase(Base):
    __tablename__ = "dispute_cases"

    id                    = Column(Integer, primary_key=True, index=True)
    case_id               = Column(String(64), unique=True, index=True, nullable=False)
    customer_id           = Column(String(64), index=True, nullable=False)
    customer_name         = Column(String(256), nullable=True)
    email                 = Column(String(256), nullable=True)
    phone                 = Column(String(32), nullable=True)

    # Transaction details
    transaction_id        = Column(String(128), index=True, nullable=False)
    transaction_type      = Column(String(64), nullable=False)
    merchant              = Column(String(256), nullable=True)
    amount                = Column(Float, nullable=False)
    currency              = Column(String(8), default="INR")
    transaction_date      = Column(String(32), nullable=True)
    transaction_time      = Column(String(32), nullable=True)

    # Customer input
    customer_comment      = Column(Text, nullable=True)
    dispute_reason        = Column(String(256), nullable=True)
    fraud_selected        = Column(Boolean, default=False)

    # AI Analysis outputs
    dispute_category      = Column(String(128), nullable=True, index=True)
    fraud_suspicion       = Column(Boolean, default=False, index=True)
    customer_intent_summary = Column(Text, nullable=True)
    priority              = Column(String(32), default="MEDIUM", index=True)
    confidence_score      = Column(Float, default=0.0)
    risk_tags             = Column(JSON, default=list)
    structured_reasoning  = Column(Text, nullable=True)

    # Workflow metadata
    status                = Column(String(64), default="Dispute Raised", index=True)
    workflow_ready        = Column(Boolean, default=False)
    current_stage         = Column(String(64), default="intake")

    # ── Enterprise fields ──────────────────────────────────────────────────────

    # Queue & assignment
    assigned_queue        = Column(String(64), nullable=True, index=True)
    assigned_analyst      = Column(String(128), nullable=True, index=True)

    # Priority scoring (weighted numeric, higher = more urgent)
    priority_score        = Column(Float, default=0.0)

    # SLA tracking
    sla_deadline          = Column(DateTime, nullable=True)
    sla_breached          = Column(Boolean, default=False)
    sla_paused_at         = Column(DateTime, nullable=True)   # non-null when SLA is paused

    # Duplicate detection
    duplicate_of          = Column(String(64), nullable=True)  # case_id of original if duplicate

    # Manual review flag
    requires_manual_review = Column(Boolean, default=False)
    manual_review_reason  = Column(Text, nullable=True)

    # Case lock (pessimistic locking for concurrent analysts)
    locked_by             = Column(String(128), nullable=True)
    locked_at             = Column(DateTime, nullable=True)

    # Evidence verification (LLM verdict on attached documents)
    evidence_match        = Column(Boolean, nullable=True)   # null = no docs, true/false = match verdict
    evidence_match_note   = Column(Text, nullable=True)

    # Investigation plan (Agent 2 — IIA output, full JSON)
    investigation_plan    = Column(JSON, nullable=True)

    # Agent 1 audit trail (ARIA — tools called, performance, metadata)
    confidence_factors    = Column(JSON, default=list)
    tools_used            = Column(JSON, default=list)
    agent_metadata        = Column(JSON, nullable=True)
    metrics               = Column(JSON, nullable=True)

    # Agent 1 fallback resilience — set when LLM was unavailable at submission time
    fallback_mode         = Column(Boolean, default=False)
    failure_reason        = Column(String(64), nullable=True)

    # Agent 3 — WOA (Workflow Orchestration Agent) output
    workflow_plan         = Column(JSON, nullable=True)

    # Identity & Trust Intelligence Agent outputs
    trust_intelligence    = Column(JSON, nullable=True)
    user_trust_score      = Column(Float, default=1.0)
    behavioral_risk_score = Column(Float, default=0.0)
    identity_status       = Column(String(64), default="PENDING")

    # Fraud Reasoning Agent outputs
    fraud_reasoning_brief = Column(JSON, nullable=True)
    fraud_probability     = Column(Float, default=0.0)
    fraud_risk_level      = Column(String(32), default="LOW")

    # Agent 4 — EIA (Evidence Intelligence Agent) output
    evidence_assessment   = Column(JSON, nullable=True)

    # Supporting evidence (raw form fields for re-analysis)
    transaction_metadata  = Column(JSON, default=dict)

    # Timestamps — indexed because every list query orders by created_at
    created_at            = Column(DateTime, default=_utc_now, nullable=False, index=True)
    updated_at            = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    # Relationships
    audit_logs            = relationship("AuditLog", back_populates="dispute_case", cascade="all, delete-orphan")
    workflow_states       = relationship("WorkflowState", back_populates="dispute_case", cascade="all, delete-orphan")
    case_notes            = relationship("CaseNote", back_populates="dispute_case", cascade="all, delete-orphan")
    document_requests     = relationship("DocumentRequest", back_populates="dispute_case", cascade="all, delete-orphan")
    communication_logs    = relationship("CommunicationLog", back_populates="dispute_case", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "email": self.email,
            "phone": self.phone,
            "transaction_id": self.transaction_id,
            "transaction_type": self.transaction_type,
            "merchant": self.merchant,
            "amount": self.amount,
            "currency": self.currency,
            "transaction_date": self.transaction_date,
            "transaction_time": self.transaction_time,
            "customer_comment": self.customer_comment,
            "dispute_reason": self.dispute_reason,
            "fraud_selected": self.fraud_selected,
            "dispute_category": self.dispute_category,
            "fraud_suspicion": self.fraud_suspicion,
            "customer_intent_summary": self.customer_intent_summary,
            "priority": self.priority,
            "confidence_score": self.confidence_score,
            "risk_tags": self.risk_tags or [],
            "structured_reasoning": self.structured_reasoning,
            "evidence_match": self.evidence_match,
            "evidence_match_note": self.evidence_match_note,
            "status": self.status,
            "workflow_ready": self.workflow_ready,
            # Enterprise fields
            "assigned_queue": self.assigned_queue,
            "assigned_analyst": self.assigned_analyst,
            "priority_score": self.priority_score or 0.0,
            "sla_deadline": _iso(self.sla_deadline),
            "sla_breached": self.sla_breached or False,
            "sla_paused_at": _iso(self.sla_paused_at),
            "duplicate_of": self.duplicate_of,
            "requires_manual_review": self.requires_manual_review or False,
            "manual_review_reason": self.manual_review_reason,
            "locked_by": self.locked_by,
            "locked_at": _iso(self.locked_at),
            "transaction_metadata": self.transaction_metadata or {},
            "investigation_plan": self.investigation_plan,
            "confidence_factors": self.confidence_factors or [],
            "tools_used": self.tools_used or [],
            "agent_metadata": self.agent_metadata,
            "metrics": self.metrics,
            "fallback_mode": self.fallback_mode or False,
            "failure_reason": self.failure_reason,
            "workflow_plan": self.workflow_plan,
            "trust_intelligence": self.trust_intelligence,
            "user_trust_score": self.user_trust_score,
            "behavioral_risk_score": self.behavioral_risk_score,
            "identity_status": self.identity_status,
            "fraud_reasoning_brief": self.fraud_reasoning_brief,
            "fraud_probability": self.fraud_probability,
            "fraud_risk_level": self.fraud_risk_level,
            "evidence_assessment": self.evidence_assessment,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable append-only audit trail. Never update or delete rows."""
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)
    case_id     = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    event_type  = Column(String(128), nullable=False)
    stage       = Column(String(64), nullable=True)
    actor       = Column(String(64), default="system")
    payload     = Column(JSON, nullable=True)
    message     = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=_utc_now, nullable=False)

    dispute_case = relationship("DisputeCase", back_populates="audit_logs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "event_type": self.event_type,
            "stage": self.stage,
            "actor": self.actor,
            "payload": self.payload,
            "message": self.message,
            "created_at": _iso(self.created_at),
        }


# ── Workflow States ───────────────────────────────────────────────────────────

class WorkflowState(Base):
    """Snapshot of LangGraph workflow state at each node transition."""
    __tablename__ = "workflow_states"

    id              = Column(Integer, primary_key=True, index=True)
    case_id         = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    node_name       = Column(String(128), nullable=False)
    input_state     = Column(JSON, nullable=True)
    output_state    = Column(JSON, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    success         = Column(Boolean, default=True)
    error_message   = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=_utc_now, nullable=False)

    dispute_case    = relationship("DisputeCase", back_populates="workflow_states")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "node_name": self.node_name,
            "execution_time_ms": self.execution_time_ms,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": _iso(self.created_at),
        }


# ── Case Notes ────────────────────────────────────────────────────────────────

class CaseNote(Base):
    """Analyst notes attached to a dispute case. Append-only."""
    __tablename__ = "case_notes"

    id          = Column(Integer, primary_key=True, index=True)
    case_id     = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    analyst     = Column(String(128), nullable=False)
    note        = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=True)   # False = visible to customer
    created_at  = Column(DateTime, default=_utc_now, nullable=False)

    dispute_case = relationship("DisputeCase", back_populates="case_notes")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "analyst": self.analyst,
            "note": self.note,
            "is_internal": self.is_internal,
            "created_at": _iso(self.created_at),
        }


# ── Document Requests ─────────────────────────────────────────────────────────

class DocumentRequest(Base):
    """Formal request for additional documents from the customer."""
    __tablename__ = "document_requests"

    id              = Column(Integer, primary_key=True, index=True)
    case_id         = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    requested_by    = Column(String(128), nullable=False)
    document_type   = Column(String(256), nullable=False)   # e.g. "Bank Statement", "Police FIR"
    description     = Column(Text, nullable=True)
    due_date        = Column(DateTime, nullable=True)
    fulfilled       = Column(Boolean, default=False)
    fulfilled_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=_utc_now, nullable=False)

    dispute_case    = relationship("DisputeCase", back_populates="document_requests")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "requested_by": self.requested_by,
            "document_type": self.document_type,
            "description": self.description,
            "due_date": _iso(self.due_date),
            "fulfilled": self.fulfilled,
            "fulfilled_at": _iso(self.fulfilled_at),
            "created_at": _iso(self.created_at),
        }


# ── Communication Logs ────────────────────────────────────────────────────────

class CommunicationLog(Base):
    """Every customer-facing notification generated by the Communication Agent."""
    __tablename__ = "communication_logs"

    id                = Column(Integer, primary_key=True, index=True)
    case_id           = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    notification_type = Column(String(64), nullable=False)   # CASE_RECEIVED / INVESTIGATION_STARTED / etc.
    recipient         = Column(String(256), nullable=False)
    subject           = Column(String(512), nullable=False)
    body              = Column(Text, nullable=False)
    status            = Column(String(32), default="SENT")   # SENT / FAILED / PENDING
    sent_at           = Column(DateTime, nullable=True)
    created_at        = Column(DateTime, default=_utc_now, nullable=False)

    dispute_case      = relationship("DisputeCase", back_populates="communication_logs")

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "case_id":           self.case_id,
            "notification_type": self.notification_type,
            "recipient":         self.recipient,
            "subject":           self.subject,
            "body":              self.body,
            "status":            self.status,
            "sent_at":           _iso(self.sent_at),
            "created_at":        _iso(self.created_at),
        }


# ── Account Events ─────────────────────────────────────────────────────────────

class AccountEvent(Base):
    """Bank system security events — password resets, device registrations, etc."""
    __tablename__ = "account_events"

    event_id        = Column(String(64), primary_key=True, index=True)
    customer_id     = Column(String(64), index=True, nullable=False)
    event_type      = Column(String(64), nullable=False, index=True)
    event_timestamp = Column(DateTime, nullable=False, index=True)
    metadata_json   = Column(JSON, default=dict)
    created_at      = Column(DateTime, default=_utc_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "event_id":        self.event_id,
            "customer_id":     self.customer_id,
            "event_type":      self.event_type,
            "event_timestamp": _iso(self.event_timestamp),
            "metadata_json":   self.metadata_json or {},
        }


# ── Customer Devices ───────────────────────────────────────────────────────────

class CustomerDevice(Base):
    """Registered devices per customer — used for device trust scoring."""
    __tablename__ = "customer_devices"

    id           = Column(Integer, primary_key=True, index=True)
    device_id    = Column(String(64), index=True, nullable=False)
    customer_id  = Column(String(64), index=True, nullable=False)
    device_name  = Column(String(128), nullable=True)
    first_seen   = Column(DateTime, nullable=False)
    last_seen    = Column(DateTime, nullable=True)
    trusted      = Column(Boolean, default=False)
    location     = Column(String(128), nullable=True)
    created_at   = Column(DateTime, default=_utc_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "device_id":   self.device_id,
            "customer_id": self.customer_id,
            "device_name": self.device_name,
            "first_seen":  _iso(self.first_seen),
            "last_seen":   _iso(self.last_seen),
            "trusted":     self.trusted,
            "location":    self.location,
        }


# ── Beneficiaries ──────────────────────────────────────────────────────────────

class Beneficiary(Base):
    """Known beneficiaries / payees per customer."""
    __tablename__ = "beneficiaries"

    id                = Column(Integer, primary_key=True, index=True)
    customer_id       = Column(String(64), index=True, nullable=False)
    beneficiary_name  = Column(String(256), nullable=False)
    beneficiary_id    = Column(String(128), nullable=True)
    created_at        = Column(DateTime, default=_utc_now, nullable=False)
    last_used_at      = Column(DateTime, nullable=True)
    transaction_count = Column(Integer, default=0)
    trusted           = Column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "customer_id":       self.customer_id,
            "beneficiary_name":  self.beneficiary_name,
            "beneficiary_id":    self.beneficiary_id,
            "created_at":        _iso(self.created_at),
            "last_used_at":      _iso(self.last_used_at),
            "transaction_count": self.transaction_count,
            "trusted":           self.trusted,
        }
