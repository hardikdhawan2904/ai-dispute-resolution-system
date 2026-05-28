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


class CaseNoteResponse(BaseModel):
    id: int
    case_id: str
    analyst: str
    note: str
    is_internal: bool
    created_at: str


# ── Document Requests ─────────────────────────────────────────────────────────

class CreateDocumentRequestBody(BaseModel):
    requested_by: str = Field(..., min_length=1, max_length=128)
    document_type: str = Field(..., min_length=2, max_length=256)
    description: Optional[str] = None
    due_date: Optional[datetime] = None


class DocumentRequestResponse(BaseModel):
    id: int
    case_id: str
    requested_by: str
    document_type: str
    description: Optional[str]
    due_date: Optional[str]
    fulfilled: bool
    fulfilled_at: Optional[str]
    created_at: str


# ── Case Lock ─────────────────────────────────────────────────────────────────

class AcquireLockRequest(BaseModel):
    analyst: str = Field(..., min_length=1, max_length=128)


class LockResponse(BaseModel):
    acquired: bool
    locked_by: Optional[str] = None
    locked_at: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


# ── Analyst Actions ───────────────────────────────────────────────────────────

class AnalystActionRequest(BaseModel):
    action: str = Field(..., description="approve | reject | escalate | reassign | mark_sla_breach | under_investigation")
    analyst: str = Field(..., min_length=1, max_length=128)
    note: Optional[str] = None
    new_assignee: Optional[str] = None
    new_queue: Optional[str] = None


# ── Queue ─────────────────────────────────────────────────────────────────────

class QueueSummary(BaseModel):
    queue: str
    display: str
    count: int
    critical: int
    sla_breached: int


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
