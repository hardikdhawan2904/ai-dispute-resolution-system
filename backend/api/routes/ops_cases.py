"""
Ops-facing case management endpoints.

Covers: notes, document requests, locks, analyst actions, investigation timeline,
risk explanations, and advanced search.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from sqlalchemy.orm import Session

from database.database import get_db
from database.models import DisputeCase
from schemas.ops_schemas import (
    AddNoteRequest,
    CreateDocumentRequestBody,
    AcquireLockRequest,
    AnalystActionRequest,
    CaseSearchRequest,
)
from services import (
    case_note_service,
    document_request_service,
    case_lock_service,
    analyst_actions_service,
    investigation_timeline_service,
    risk_explanation_service,
    case_search_service,
)

router = APIRouter(prefix="/api/ops/cases", tags=["Ops — Cases"])


# ── Case notes ────────────────────────────────────────────────────────────────

@router.get("/{case_id}/notes")
def get_notes(case_id: str, include_internal: bool = True, db: Session = Depends(get_db)):
    return {"case_id": case_id, "notes": case_note_service.get_notes(case_id, db, include_internal)}


@router.post("/{case_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(case_id: str, body: AddNoteRequest, db: Session = Depends(get_db)):
    result = case_note_service.add_note(
        case_id, body.analyst, body.note, body.is_internal, db
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return result


# ── Document requests ─────────────────────────────────────────────────────────

@router.get("/{case_id}/document-requests")
def get_document_requests(case_id: str, db: Session = Depends(get_db)):
    return {"case_id": case_id, "requests": document_request_service.get_requests(case_id, db)}


@router.post("/{case_id}/document-requests", status_code=status.HTTP_201_CREATED)
def create_document_request(case_id: str, body: CreateDocumentRequestBody, db: Session = Depends(get_db)):
    result = document_request_service.create_request(
        case_id, body.requested_by, body.document_type,
        body.description or "", body.due_date, db,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return result


@router.post("/document-requests/{request_id}/fulfill")
def fulfill_document_request(request_id: int, db: Session = Depends(get_db)):
    result = document_request_service.fulfill_request(request_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or already fulfilled")
    return result


# ── Case lock ─────────────────────────────────────────────────────────────────

@router.get("/{case_id}/lock")
def check_lock(case_id: str, db: Session = Depends(get_db)):
    return case_lock_service.check_lock(case_id, db)


@router.post("/{case_id}/lock")
def acquire_lock(case_id: str, body: AcquireLockRequest, db: Session = Depends(get_db)):
    return case_lock_service.acquire_lock(case_id, body.analyst, db)


@router.delete("/{case_id}/lock")
def release_lock(case_id: str, analyst: str = Query(...), db: Session = Depends(get_db)):
    released = case_lock_service.release_lock(case_id, analyst, db)
    return {"released": released}


# ── Analyst actions ───────────────────────────────────────────────────────────

@router.post("/{case_id}/actions")
def analyst_action(case_id: str, body: AnalystActionRequest, db: Session = Depends(get_db)):
    result = analyst_actions_service.perform_action(
        case_id=case_id,
        action=body.action,
        analyst=body.analyst,
        db=db,
        note=body.note or "",
        new_assignee=body.new_assignee or "",
        new_queue=body.new_queue or "",
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return result


# ── Investigation timeline ────────────────────────────────────────────────────

@router.get("/{case_id}/timeline")
def get_timeline(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {
        "case_id": case_id,
        "timeline": investigation_timeline_service.build_timeline(case_id, db),
    }


# ── Risk explanation ──────────────────────────────────────────────────────────

@router.get("/{case_id}/risk-explanation")
def get_risk_explanation(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    case_dict = case.to_dict()
    return {
        "case_id": case_id,
        "risk_indicators": risk_explanation_service.explain_risk(case_dict),
        "investigation_summary": risk_explanation_service.get_investigation_summary(case_dict),
    }


# ── Advanced search ───────────────────────────────────────────────────────────

@router.post("/search")
def search_cases(body: CaseSearchRequest, db: Session = Depends(get_db)):
    result = case_search_service.search_cases(
        db=db,
        query=body.query,
        status=body.status,
        priority=body.priority,
        category=body.category,
        queue=body.queue,
        analyst=body.analyst,
        fraud_only=body.fraud_only,
        manual_review_only=body.manual_review_only,
        sla_breached_only=body.sla_breached_only,
        min_amount=body.min_amount,
        max_amount=body.max_amount,
        skip=body.skip,
        limit=body.limit,
    )
    return result
