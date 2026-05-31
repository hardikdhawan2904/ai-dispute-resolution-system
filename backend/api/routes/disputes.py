"""
Dispute API routes — all endpoints for the BFSI dispute resolution platform.
"""
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
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
async def submit_dispute_public(
    payload: str = Form(...),
    files: List[UploadFile] = File(default=[]),
):
    """
    Public dispute submission — accepts form data + optional evidence files in one request.

    Evidence text is extracted from files BEFORE the LLM is called so everything
    (form fields + document content) goes to the model in a single call.
    Broadcasts DISPUTE_QUEUED immediately, then ANALYSIS_COMPLETE after the pipeline finishes.
    """
    from utils.extractor import extract_text

    data = DisputeSubmissionRequest.model_validate_json(payload).model_dump()
    case_id = generate_case_id()

    await ws_manager.broadcast({
        "type":          "DISPUTE_QUEUED",
        "case_id":       case_id,
        "customer_id":   data.get("customer_id", ""),
        "customer_name": data.get("customer_name", ""),
        "merchant":      data.get("merchant", ""),
        "amount":        data.get("amount", 0),
        "currency":      data.get("currency", "INR"),
        "timestamp":     utc_now_iso(),
    })

    # Extract text from evidence files before calling the LLM
    document_texts: List[str] = []
    if files:
        upload_dir = _UPLOAD_ROOT / case_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            ext = Path(file.filename or "").suffix.lower()
            if ext not in _ALLOWED_EXTENSIONS:
                continue
            content = await file.read()
            if len(content) > _MAX_FILE_BYTES:
                continue
            safe_name = Path(file.filename).name
            dest = upload_dir / safe_name
            dest.write_bytes(content)
            text = extract_text(str(dest))
            if text.strip():
                document_texts.append(f"[{safe_name}]\n{text}")

    data["_preset_case_id"] = case_id

    def _run_sync():
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            return DisputeService.submit_dispute(data, db, document_texts=document_texts)
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_sync)

    if not result["success"]:
        await ws_manager.broadcast({
            "type":    "ANALYSIS_FAILED",
            "case_id": case_id,
            "errors":  result["errors"],
        })
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Dispute submission failed validation", "errors": result["errors"]},
        )

    await ws_manager.broadcast({
        "type":    "ANALYSIS_COMPLETE",
        "case_id": result["case_id"],
        "case":    result["final_case"],
    })

    api_logger.info(f"Dispute submitted: {result['case_id']}")

    return {
        "success":  True,
        "case_id":  result["case_id"],
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
    Store additional documents against an existing case.
    Files are saved to disk and logged — no LLM re-run.
    Evidence should be submitted together with the form via /submit-public.
    """
    from database.models import DisputeCase, AuditLog

    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    upload_dir = _UPLOAD_ROOT / case_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: List[str] = []
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

    if saved:
        db.add(AuditLog(
            case_id=case_id,
            event_type="DOCUMENT_UPLOADED",
            actor="customer",
            message=f"Customer uploaded {len(saved)} document(s): {', '.join(saved)}",
            payload={"files": saved, "count": len(saved)},
        ))
        db.commit()
        api_logger.info(f"Documents saved for {case_id}: {saved}")

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
        "evidence_match": case.get("evidence_match"),
        "evidence_match_note": case.get("evidence_match_note"),
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
