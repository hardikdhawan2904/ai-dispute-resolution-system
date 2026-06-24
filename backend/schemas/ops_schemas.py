"""Pydantic schemas for the ops-facing API endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Case Notes ────────────────────────────────────────────────────────────────

class AddNoteRequest(BaseModel):
    analyst: str = Field(..., min_length=1, max_length=128)
    note: str = Field(..., min_length=1, max_length=4000)
    is_internal: bool = True


class CreateDocumentRequestBody(BaseModel):
    requested_by: str = Field(..., min_length=1, max_length=128)
    document_type: str = Field(..., min_length=2, max_length=256)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    notify: bool = True
    notify_docs: Optional[List[str]] = None  # exact list to show in email


# ── Case Lock ─────────────────────────────────────────────────────────────────

class AcquireLockRequest(BaseModel):
    analyst: str = Field(..., min_length=1, max_length=128)


# ── Analyst Actions ───────────────────────────────────────────────────────────

class AnalystActionRequest(BaseModel):
    action: str = Field(..., description="approve | reject | escalate | reassign | mark_sla_breach | under_investigation")
    analyst: str = Field(..., min_length=1, max_length=128)
    note: Optional[str] = None
    new_assignee: Optional[str] = None
    new_queue: Optional[str] = None


# ── Queue ─────────────────────────────────────────────────────────────────────

# ── Search ────────────────────────────────────────────────────────────────────

class CaseSearchRequest(BaseModel):
    query: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    queue: Optional[str] = None
    analyst: Optional[str] = None
    fraud_only: bool = False
    manual_review_only: bool = False
    sla_breached_only: bool = False
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    skip: int = 0
    limit: int = 50


# ── Analytics ─────────────────────────────────────────────────────────────────

class OpsAnalyticsResponse(BaseModel):
    total_cases: int
    open_cases: int
    fraud_cases: int
    critical_cases: int
    sla_breached_cases: int
    manual_review_cases: int
    resolved_cases: int
    resolution_rate: float
    new_cases_7d: int
    new_cases_30d: int
    avg_confidence_score: float
    by_queue: dict
    by_status: dict
    by_priority: dict
    by_category: dict
    # Agent 4 — EIA evidence metrics
    evidence_reviews_pending:   int = 0
    evidence_reviews_completed: int = 0
    blocked_investigations:     int = 0
    avg_evidence_completeness:  float = 0.0

