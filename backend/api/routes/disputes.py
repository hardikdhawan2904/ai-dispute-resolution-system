"""
Dispute API routes — all endpoints for the BFSI dispute resolution platform.
"""
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from database.database import get_db
from services.dispute_service import DisputeService
from schemas.dispute_schemas import (
    DisputeSubmissionRequest,
    DisputeSubmissionResponse,
    DisputeCaseResponse,
    CasesListResponse,
    DashboardStatsResponse,
    StatusUpdateRequest,
    AuditLogResponse,
    WorkflowStateResponse,
)
from api.websocket_manager import ws_manager
from utils.helpers import generate_case_id, utc_now_iso
from utils.logger import api_logger

router = APIRouter(prefix="/api/disputes", tags=["Disputes"])

_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".csv"}
_MAX_FILE_BYTES     = 10 * 1024 * 1024          # 10 MB
_UPLOAD_ROOT        = Path("uploads")


@router.post("/submit-public", status_code=status.HTTP_201_CREATED)
async def submit_dispute_public(payload: DisputeSubmissionRequest):
    """
    Public dispute submission — no auth required.

    Immediately broadcasts DISPUTE_QUEUED so the internal review dashboard
    shows the incoming case at once. Runs LangGraph in a thread executor,
    then broadcasts ANALYSIS_COMPLETE with full AI data.

    Returns only case_id + message to the submitter.
    """
    case_id = generate_case_id()

    await ws_manager.broadcast({
        "type": "DISPUTE_QUEUED",
        "case_id": case_id,
        "customer_id": payload.customer_id,
        "customer_name": getattr(payload, "customer_name", ""),
        "merchant": payload.merchant,
        "amount": payload.amount,
        "currency": getattr(payload, "currency", "INR"),
        "timestamp": utc_now_iso(),
    })

    data = payload.model_dump()
    data["_preset_case_id"] = case_id

    def _run_sync():
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            return DisputeService.submit_dispute(data, db)
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_sync)

    if not result["success"]:
        await ws_manager.broadcast({
            "type": "ANALYSIS_FAILED",
            "case_id": case_id,
            "errors": result["errors"],
        })
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Dispute submission failed validation", "errors": result["errors"]},
        )

    await ws_manager.broadcast({
        "type": "ANALYSIS_COMPLETE",
        "case_id": result["case_id"],
        "case": result["final_case"],
    })

    api_logger.info(f"Dispute submitted: {result['case_id']}")

    return {
        "success": True,
        "case_id": result["case_id"],
        "message": (
            "Your dispute has been submitted successfully and is now under review. "
            "Our team will investigate and contact you within 5–7 business days."
        ),
    }


@router.get("/cases", response_model=CasesListResponse)
def list_cases(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    fraud_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    result = DisputeService.list_cases(
        db, skip=skip, limit=limit, status=status, priority=priority,
        category=category, fraud_only=fraud_only,
    )
    return CasesListResponse(
        total=result["total"],
        cases=[DisputeCaseResponse(**_safe_case_dict(c)) for c in result["cases"]],
    )


@router.get("/stats", response_model=DashboardStatsResponse)
def dashboard_stats(db: Session = Depends(get_db)):
    stats = DisputeService.get_dashboard_stats(db)
    recent = [DisputeCaseResponse(**_safe_case_dict(c)) for c in stats.pop("recent_cases", [])]
    return DashboardStatsResponse(**stats, recent_cases=recent)


@router.get("/cases/{case_id}", response_model=DisputeCaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = DisputeService.get_case(case_id, db)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return DisputeCaseResponse(**_safe_case_dict(case))


@router.put("/cases/{case_id}/status", response_model=DisputeCaseResponse)
def update_case_status(case_id: str, body: StatusUpdateRequest, db: Session = Depends(get_db)):
    updated = DisputeService.update_status(case_id, body.status, body.actor, body.note, db)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return DisputeCaseResponse(**_safe_case_dict(updated))


@router.get("/cases/{case_id}/audit-logs")
def get_audit_logs(case_id: str, db: Session = Depends(get_db)):
    logs = DisputeService.get_audit_logs(case_id, db)
    if not logs and not DisputeService.get_case(case_id, db):
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"case_id": case_id, "audit_logs": logs}


@router.get("/cases/{case_id}/workflow-states")
def get_workflow_states(case_id: str, db: Session = Depends(get_db)):
    states = DisputeService.get_workflow_states(case_id, db)
    return {"case_id": case_id, "workflow_states": states}


@router.get("/audit-logs")
def get_all_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    from database.models import AuditLog
    from sqlalchemy import desc as _desc
    logs = db.query(AuditLog).order_by(_desc(AuditLog.created_at)).limit(limit).all()
    return {"audit_logs": [log.to_dict() for log in logs]}


@router.post("/cases/{case_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_case_documents(
    case_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Public endpoint — customers upload supporting documents after submitting a dispute.
    Accepts PDF, JPG, PNG, XLSX (max 10 MB per file).
    After saving all files, text is extracted from each (OCR for images, pdfplumber for PDF,
    openpyxl for XLSX) and fed into a single unified dispute analysis call.
    """
    from database.models import DisputeCase, AuditLog
    from agents.dispute_agent import run_dispute_agent
    from utils.extractor import extract_text

    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    upload_dir = _UPLOAD_ROOT / case_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: List[str] = []

    # ── Save all files first ──────────────────────────────────────────────
    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"File type '{ext}' is not allowed. Allowed: PDF, JPG, PNG, XLSX",
            )
        content = await upload.read()
        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"'{upload.filename}' exceeds the 10 MB file size limit",
            )
        safe_name = Path(upload.filename).name
        (upload_dir / safe_name).write_bytes(content)
        saved.append(safe_name)

    if not saved:
        return {"case_id": case_id, "uploaded": [], "count": 0}

    # ── Extract text from every uploaded file ─────────────────────────────
    document_texts = []
    for name in saved:
        text = extract_text(str(upload_dir / name))
        if text.strip():
            document_texts.append(f"[{name}]\n{text}")

    # ── Unified analysis: form data + all extracted document texts ────────
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

    # ── Persist updated analysis ──────────────────────────────────────────
    case.dispute_category        = result.get("dispute_category", case.dispute_category)
    case.fraud_suspicion         = result.get("fraud_suspicion", case.fraud_suspicion)
    case.customer_intent_summary = result.get("customer_intent_summary", case.customer_intent_summary)
    case.confidence_score        = result.get("confidence_score", case.confidence_score)
    case.risk_tags               = result.get("risk_tags", case.risk_tags)
    case.structured_reasoning    = result.get("structured_reasoning", case.structured_reasoning)

    db.add(AuditLog(
        case_id=case_id,
        event_type="DOCUMENT_UPLOADED",
        actor="customer",
        message=f"Customer uploaded {len(saved)} document(s): {', '.join(saved)}",
        payload={"files": saved, "count": len(saved)},
    ))
    db.add(AuditLog(
        case_id=case_id,
        event_type="REANALYSED",
        actor="system",
        message=f"Unified analysis complete with {len(document_texts)} document(s). Confidence: {case.confidence_score:.0%}",
        payload={
            "files": saved,
            "documents_with_text": len(document_texts),
            "confidence_score": case.confidence_score,
            "dispute_category": case.dispute_category,
        },
    ))

    db.commit()
    api_logger.info(f"Unified analysis complete for {case_id}: {len(document_texts)} docs extracted")

    return {"case_id": case_id, "uploaded": saved, "count": len(saved)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_case_dict(case: dict) -> dict:
    return {
        "case_id": case.get("case_id", ""),
        "customer_id": case.get("customer_id", ""),
        "customer_name": case.get("customer_name"),
        "email": case.get("email"),
        "phone": case.get("phone"),
        "transaction_id": case.get("transaction_id", ""),
        "transaction_type": case.get("transaction_type", ""),
        "merchant": case.get("merchant", ""),
        "amount": case.get("amount", 0.0),
        "currency": case.get("currency", "INR"),
        "transaction_date": case.get("transaction_date"),
        "transaction_time": case.get("transaction_time"),
        "customer_comment": case.get("customer_comment"),
        "dispute_reason": case.get("dispute_reason"),
        "fraud_selected": case.get("fraud_selected", False),
        "dispute_category": case.get("dispute_category"),
        "fraud_suspicion": case.get("fraud_suspicion", False),
        "customer_intent_summary": case.get("customer_intent_summary"),
        "priority": case.get("priority", "MEDIUM"),
        "confidence_score": case.get("confidence_score", 0.0),
        "risk_tags": case.get("risk_tags", []),
        "structured_reasoning": case.get("structured_reasoning"),
        "status": case.get("status", "Dispute Raised"),
        "workflow_ready": case.get("workflow_ready", False),
        # Enterprise fields
        "assigned_queue": case.get("assigned_queue"),
        "assigned_analyst": case.get("assigned_analyst"),
        "priority_score": case.get("priority_score", 0.0),
        "sla_deadline": case.get("sla_deadline"),
        "sla_breached": case.get("sla_breached", False),
        "sla_paused_at": case.get("sla_paused_at"),
        "duplicate_of": case.get("duplicate_of"),
        "requires_manual_review": case.get("requires_manual_review", False),
        "manual_review_reason": case.get("manual_review_reason"),
        "locked_by": case.get("locked_by"),
        "locked_at": case.get("locked_at"),
        "created_at": case.get("created_at") or "",
        "updated_at": case.get("updated_at"),
    }
