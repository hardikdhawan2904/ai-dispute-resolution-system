"""
Ops-facing case management endpoints.

Covers: notes, document requests, locks, analyst actions, investigation timeline,
risk explanations, and advanced search.
"""
import pathlib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from sqlalchemy.orm import Session

from database.database import get_db
from database.models import DisputeCase, AuditLog, WorkflowState, CaseNote, DocumentRequest
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
from services import priority_engine, manual_review_service
from agents.dispute_agent import run_dispute_agent

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


# ── Re-analyse ───────────────────────────────────────────────────────────────

@router.post("/{case_id}/reanalyse")
def reanalyse_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    dispute_input = {
        "case_id":          case.case_id,
        "customer_name":    case.customer_name,
        "customer_id":      case.customer_id,
        "email":            case.email or "",
        "phone":            case.phone or "",
        "transaction_id":   case.transaction_id,
        "transaction_type": case.transaction_type,
        "merchant":         case.merchant,
        "amount":           case.amount,
        "currency":         case.currency,
        "transaction_date": case.transaction_date or "",
        "transaction_time": case.transaction_time or "",
        "dispute_reason":   case.dispute_reason or "",
        "fraud_selected":   case.fraud_suspicion,
        "customer_comment": case.customer_comment or "",
        "transaction_metadata": case.transaction_metadata or {},
    }

    result = run_dispute_agent(dispute_input)

    case.dispute_category        = result.get("dispute_category", case.dispute_category)
    case.fraud_suspicion         = result.get("fraud_suspicion", case.fraud_suspicion)
    case.customer_intent_summary = result.get("customer_intent_summary", case.customer_intent_summary)
    case.confidence_score        = result.get("confidence_score", case.confidence_score)
    case.risk_tags               = result.get("risk_tags", case.risk_tags)
    case.structured_reasoning    = result.get("structured_reasoning", case.structured_reasoning)

    priority_score, priority_label = priority_engine.compute_priority(case.to_dict())
    case.priority_score = priority_score
    case.priority       = priority_label

    flag, reason = manual_review_service.should_flag_manual_review(case.to_dict())
    case.requires_manual_review = flag
    case.manual_review_reason   = reason if flag else None

    log = AuditLog(
        case_id=case_id,
        event_type="REANALYSED",
        stage="structured_output",
        actor="system",
        message=f"Case re-analysed. New confidence: {case.confidence_score:.0%}, Priority: {case.priority}",
        payload={"confidence_score": case.confidence_score, "priority": case.priority},
    )
    db.add(log)
    db.commit()
    db.refresh(case)
    return case.to_dict()


# ── Uploaded evidence files ───────────────────────────────────────────────────

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_UPLOADS_ROOT = pathlib.Path("uploads")

@router.get("/{case_id}/uploads")
def list_uploads(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = _UPLOADS_ROOT / case_id
    if not case_dir.exists():
        return {"case_id": case_id, "files": []}

    files = []
    for f in sorted(case_dir.iterdir()):
        if not f.is_file():
            continue
        files.append({
            "name": f.name,
            "url": f"/uploads/{case_id}/{f.name}",
            "is_image": f.suffix.lower() in _IMAGE_EXTS,
        })

    return {"case_id": case_id, "files": files}


@router.post("/{case_id}/uploads/analyse")
def analyse_uploads(case_id: str, db: Session = Depends(get_db)):
    """Re-run unified analysis on all uploaded files for a case."""
    from agents.dispute_agent import run_dispute_agent
    from utils.extractor import extract_text

    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = _UPLOADS_ROOT / case_id
    if not case_dir.exists():
        return {"case_id": case_id, "analysed": 0, "files": []}

    # ── Extract text from every file in the case directory ────────────────
    _ANALYSABLE = _IMAGE_EXTS | {".pdf", ".xlsx", ".csv"}
    document_texts = []
    analysed = 0
    for file_path in sorted(case_dir.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in _ANALYSABLE:
            continue
        text = extract_text(str(file_path))
        if text.strip():
            document_texts.append(f"[{file_path.name}]\n{text}")
            analysed += 1

    # ── Unified analysis: form data + all extracted texts ─────────────────
    dispute_input = {
        "case_id":             case_id,
        "customer_id":         case.customer_id,
        "customer_name":       case.customer_name,
        "email":               case.email or "",
        "phone":               case.phone or "",
        "transaction_id":      case.transaction_id or "",
        "transaction_type":    case.transaction_type or "",
        "merchant":            case.merchant or "",
        "amount":              case.amount or 0,
        "currency":            case.currency or "INR",
        "transaction_date":    case.transaction_date or "",
        "transaction_time":    case.transaction_time or "",
        "dispute_reason":      case.dispute_reason or "",
        "fraud_selected":      case.fraud_suspicion or False,
        "customer_comment":    case.customer_comment or "",
        "transaction_metadata": case.transaction_metadata or {},
    }

    result = run_dispute_agent(dispute_input, document_texts=document_texts)

    case.dispute_category        = result.get("dispute_category", case.dispute_category)
    case.fraud_suspicion         = result.get("fraud_suspicion", case.fraud_suspicion)
    case.customer_intent_summary = result.get("customer_intent_summary", case.customer_intent_summary)
    case.confidence_score        = result.get("confidence_score", case.confidence_score)
    case.risk_tags               = result.get("risk_tags", case.risk_tags)
    case.structured_reasoning    = result.get("structured_reasoning", case.structured_reasoning)

    db.add(AuditLog(
        case_id=case_id,
        event_type="REANALYSED",
        actor="system",
        message=f"Unified re-analysis with {len(document_texts)} document(s). Confidence: {case.confidence_score:.0%}",
        payload={"documents_extracted": len(document_texts), "confidence_score": case.confidence_score},
    ))
    db.commit()
    db.refresh(case)

    files = []
    for f in sorted(case_dir.iterdir()):
        if f.is_file():
            files.append({
                "name": f.name,
                "url": f"/uploads/{case_id}/{f.name}",
                "is_image": f.suffix.lower() in _IMAGE_EXTS,
            })

    return {"case_id": case_id, "analysed": analysed, "files": files}


# ── Advanced search ───────────────────────────────────────────────────────────

@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    for model in [AuditLog, WorkflowState, CaseNote, DocumentRequest]:
        db.query(model).filter(model.case_id == case_id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()


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
