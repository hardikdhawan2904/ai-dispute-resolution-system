"""
SQLAlchemy ORM models for the BFSI Dispute Resolution Platform.

Tables:
  - dispute_cases     : Core dispute case with AI analysis results
  - audit_logs        : Immutable audit trail for every workflow action
  - workflow_states   : Per-case workflow execution snapshots
"""
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Boolean, Text, DateTime,
    Integer, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship

from database.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


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
    dispute_category      = Column(String(128), nullable=True)
    fraud_suspicion       = Column(Boolean, default=False)
    customer_intent_summary = Column(Text, nullable=True)
    priority              = Column(String(32), default="MEDIUM")
    confidence_score      = Column(Float, default=0.0)
    risk_tags             = Column(JSON, default=list)
    structured_reasoning  = Column(Text, nullable=True)

    # Workflow metadata
    status                = Column(String(64), default="Dispute Raised")
    workflow_ready        = Column(Boolean, default=False)
    current_stage         = Column(String(64), default="intake")

    # Timestamps
    created_at            = Column(DateTime, default=_utc_now, nullable=False)
    updated_at            = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    # Relationships
    audit_logs            = relationship("AuditLog", back_populates="dispute_case", cascade="all, delete-orphan")
    workflow_states       = relationship("WorkflowState", back_populates="dispute_case", cascade="all, delete-orphan")

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
            "status": self.status,
            "workflow_ready": self.workflow_ready,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable append-only audit trail. Never update or delete rows."""
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)
    case_id     = Column(String(64), ForeignKey("dispute_cases.case_id"), index=True, nullable=False)
    event_type  = Column(String(128), nullable=False)  # e.g. WORKFLOW_START, LLM_CALL, VALIDATION_FAIL
    stage       = Column(String(64), nullable=True)
    actor       = Column(String(64), default="system")   # system | agent | user
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
