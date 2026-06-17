"""
Dispute API routes — all endpoints for the BFSI dispute resolution platform.
"""
import asyncio
import threading
from pathlib import Path
from typing import List, Optional
from api.executor import analysis_executor
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc as _desc
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AuditLog
from services.dispute_service import DisputeService
from services.document_rules import resolve_investigation_status
from schemas.dispute_schemas import (
    DisputeSubmissionRequest,
    DisputeCaseResponse,
    CasesListResponse,
    DashboardStatsResponse,
    StatusUpdateRequest,
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
    db: Session = Depends(get_db),
):
    """
    Public dispute submission — save-first, analyse-in-background.

    Phase 1 (instant, ~1s): validate → resolve DB values → save files → save
    preliminary case record → return case_id to the user.

    Phase 2 (background): run all AI agents → enrich with priority/queue/SLA →
    update DB record → broadcast ANALYSIS_COMPLETE via WebSocket.
    """
    from utils.extractor import extract_text
    from database.models import BankCustomer, Transaction
    from pydantic import ValidationError

    try:
        data = DisputeSubmissionRequest.model_validate_json(payload).model_dump()
    except ValidationError as err:
        safe_errors = []
        for e in err.errors(include_url=False):
            safe_e = {k: v for k, v in e.items() if k != "ctx"}
            if "ctx" in e:
                safe_e["ctx"] = {ck: str(cv) for ck, cv in e["ctx"].items()}
            safe_errors.append(safe_e)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=safe_errors)

    # Always resolve customer + transaction details from DB — never trust form values.
    customer = db.query(BankCustomer).filter(
        BankCustomer.customer_id == data["customer_id"].upper()
    ).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Customer '{data['customer_id']}' not found")
    data["customer_name"] = customer.full_name
    data["email"]         = customer.email
    data["phone"]         = customer.phone

    txn = db.query(Transaction).filter(
        Transaction.transaction_id == data["transaction_id"].upper()
    ).first()
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Transaction '{data['transaction_id']}' not found")
    if txn.customer_id.upper() != data["customer_id"].upper():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Transaction does not belong to this customer")
    data["merchant"]         = txn.merchant_name
    data["amount"]           = txn.amount
    data["currency"]         = txn.currency
    data["transaction_type"] = txn.transaction_type
    data["transaction_date"] = txn.transaction_date.strftime("%Y-%m-%d") if txn.transaction_date else ""
    data["transaction_time"] = txn.transaction_date.strftime("%H:%M") if txn.transaction_date else ""

    # ── Phase 1: Save files + preliminary case record ─────────────────────────
    case_id = generate_case_id(db)
    data["_preset_case_id"] = case_id
    data["case_id"]         = case_id
    data["_document_count"] = len(files)

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

    # Save the preliminary case to DB immediately so it's visible in the queue
    db_case = DisputeService._save_preliminary_case(data, db)
    DisputeService._append_audit_log(
        db=db, case_id=case_id,
        event_type="CASE_RECEIVED", stage="intake",
        message="Case received and saved. AI analysis pipeline starting in background.",
        payload={"customer_id": data.get("customer_id"), "transaction_id": data.get("transaction_id")},
    )
    db.commit()

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

    # ── Phase 2: Run agents in a dedicated daemon thread ─────────────────────
    # BackgroundTasks shares FastAPI's thread pool — long-running agent pipelines
    # starve other requests. A daemon thread is completely independent.
    _loop = asyncio.get_event_loop()

    def _background_pipeline():
        result = DisputeService.run_pipeline(data, document_texts)
        if result.get("success"):
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast({
                "type":    "ANALYSIS_COMPLETE",
                "case_id": case_id,
                "case":    result.get("final_case"),
            }), _loop)
        else:
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast({
                "type":    "ANALYSIS_FAILED",
                "case_id": case_id,
                "errors":  result.get("errors", []),
            }), _loop)

    t = threading.Thread(target=_background_pipeline, daemon=True)
    t.start()

    api_logger.info(f"Dispute queued for background analysis: {case_id}")

    return {
        "success": True,
        "case_id": case_id,
        "message": (
            "Your dispute has been submitted successfully and is now under review. "
            "Our team will investigate and contact you within 5–7 business days."
        ),
    }


@router.get("/document-requirements")
def get_document_requirements(
    dispute_reason: str = Query(...),
    fraud_selected: bool = Query(default=False),
    amount: float = Query(default=0),
):
    """Return the required documents list for a given dispute reason.
    Called by the frontend at Step 4 (document upload) to show the customer what to upload."""
    from services.document_rules import get_customer_required_documents, infer_category
    category = infer_category(dispute_reason)
    docs = get_customer_required_documents(category, fraud_selected, amount)
    return {"category": category, "required_documents": docs}


@router.get("/cases", response_model=CasesListResponse)
def list_cases(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
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
        cases=[DisputeCaseResponse(**_list_case_dict(c)) for c in result["cases"]],
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
    logs = db.query(AuditLog).order_by(_desc(AuditLog.created_at)).limit(limit).all()
    return {"audit_logs": [log.to_dict() for log in logs]}


@router.post("/cases/{case_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_case_documents(
    case_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Store documents against a case and trigger automatic re-analysis.
    Response returns immediately; re-analysis runs in the background.
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
        # Re-evaluate status now that new files are on disk
        case.status = resolve_investigation_status(case, case_id)

        db.add(AuditLog(
            case_id=case_id,
            event_type="DOCUMENT_UPLOADED",
            actor="customer",
            message=f"Customer uploaded {len(saved)} document(s): {', '.join(saved)}. Case moved to Under Investigation.",
            payload={"files": saved, "count": len(saved)},
        ))
        db.commit()
        api_logger.info(f"Documents saved for {case_id}: {saved}")
        # Daemon thread — fully isolated from FastAPI's thread pool and event loop
        threading.Thread(target=_reanalyse_after_upload, args=(case_id,), daemon=True).start()

    return {"case_id": case_id, "uploaded": saved, "count": len(saved), "reanalysis": "queued"}


def _reanalyse_after_upload(case_id: str) -> None:
    """
    Background task: re-run Agent 1 + Agent 2 after customer uploads documents.

    DB connections are held only during fast read/write phases — never during
    LLM calls — so the connection pool is never starved.
    """
    from database.database import SessionLocal
    from database.models import DisputeCase, AuditLog
    from utils.extractor import extract_text
    from agents.dispute_agent import run_dispute_agent
    from agents.investigation_agent import run_investigation_agent
    from services.priority_engine import compute_priority
    from services.manual_review_service import should_flag_manual_review

    # ── Phase 1: verify case exists ───────────────────────────────────────────
    db = SessionLocal()
    try:
        if not db.query(DisputeCase.case_id).filter(DisputeCase.case_id == case_id).first():
            return
    finally:
        db.close()

    # ── Phase 2: extract document text (CPU, no DB) ───────────────────────────
    document_texts: List[str] = []
    upload_dir = _UPLOAD_ROOT / case_id
    if upload_dir.exists():
        for f in sorted(upload_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in _ALLOWED_EXTENSIONS:
                text = extract_text(str(f))
                if text.strip():
                    document_texts.append(f"[{f.name}]\n{text}")

    # ── Phase 3: run agents (slow LLM calls, no DB held) ─────────────────────
    from workflows.dispute_workflow import (
        _save_agent1_to_db, _save_agent2_to_db, _save_agent3_to_db,
        _save_fraud_reasoning_to_db, _save_evidence_to_db,
    )
    from agents.fraud_reasoning_agent import run_fraud_reasoning_agent
    from agents.evidence_agent import run_evidence_agent
    from agents.orchestration_agent import run_orchestration_agent

    try:
        result = run_dispute_agent({}, case_id=case_id, document_texts=document_texts)
    except Exception as exc:
        api_logger.error(f"_reanalyse_after_upload agent1 failed {case_id}: {exc}", exc_info=True)
        return

    # Persist Agent 1 results immediately so Agent 2 reads from DB (save-first)
    _save_agent1_to_db(case_id, result)

    investigation_plan = None
    try:
        # Agent 2 reads Agent 1 results from DB by case_id — not from in-memory dict
        investigation_plan = run_investigation_agent({"case_id": case_id})
        if investigation_plan:
            _save_agent2_to_db(case_id, investigation_plan)
    except Exception:
        pass

    # Agent 3 (WOA) decides which specialist agents run — it is the single source of truth
    try:
        wf_plan = run_orchestration_agent(case_id)
        if wf_plan:
            _save_agent3_to_db(case_id, wf_plan)
            workflow_path = wf_plan.get("workflow_path") or []
            if "FRAUD_AGENT" in workflow_path:
                try:
                    fraud_result = run_fraud_reasoning_agent({}, case_id=case_id)
                    if fraud_result:
                        _save_fraud_reasoning_to_db(case_id, fraud_result, wf_plan)
                except Exception as exc:
                    api_logger.error(f"_reanalyse_after_upload fraud_reasoning failed {case_id}: {exc}", exc_info=True)
            if "EVIDENCE_AGENT" in workflow_path:
                try:
                    evidence_result = run_evidence_agent(case_id)
                    if evidence_result:
                        _save_evidence_to_db(case_id, evidence_result, wf_plan)
                except Exception as exc:
                    api_logger.error(f"_reanalyse_after_upload evidence_agent failed {case_id}: {exc}", exc_info=True)
    except Exception:
        pass

    # ── Phase 4: save priority + manual-review flags, add audit log ──────────
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return

        from services.queue_assignment_service import assign_queue
        from services.sla_service import compute_sla_deadline
        case.status = resolve_investigation_status(case, case_id)
        priority_score, priority_label = compute_priority(case.to_dict())
        case.priority_score = priority_score
        case.priority       = priority_label
        case.assigned_queue = assign_queue(case.to_dict())
        case.sla_deadline   = compute_sla_deadline(priority_label)
        flag, reason = should_flag_manual_review(case.to_dict())
        case.requires_manual_review = flag
        case.manual_review_reason   = reason if flag else None

        db.add(AuditLog(
            case_id=case_id,
            event_type="REANALYSED_AFTER_UPLOAD",
            stage="structured_output",
            actor="system",
            message=(
                f"Re-analysed after document upload. "
                f"Evidence: {result.get('evidence_match')}. "
                f"Confidence: {result.get('confidence_score', 0):.0%}."
            ),
            payload={
                "confidence_score": case.confidence_score,
                "evidence_match":   case.evidence_match,
                "priority":         case.priority,
                "document_count":   len(document_texts),
            },
        ))
        updated_dict = case.to_dict()
        db.commit()
        api_logger.info(f"Re-analysis after upload complete for {case_id}")

        # Broadcast ANALYSIS_COMPLETE so the ops workspace refreshes automatically
        try:
            import asyncio
            asyncio.run(ws_manager.broadcast({
                "type":    "ANALYSIS_COMPLETE",
                "case_id": case_id,
                "case":    updated_dict,
            }))
        except Exception as ws_exc:
            api_logger.warning(f"WS broadcast failed after upload reanalysis {case_id}: {ws_exc}")

    except Exception as exc:
        api_logger.error(f"_reanalyse_after_upload save failed {case_id}: {exc}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _list_case_dict(case: dict) -> dict:
    """Lightweight dict for list endpoints — strips large JSON blobs.
    investigation_plan and workflow_plan are only fetched on case detail view."""
    return {
        "case_id":              case.get("case_id", ""),
        "customer_id":          case.get("customer_id", ""),
        "customer_name":        case.get("customer_name"),
        "transaction_id":       case.get("transaction_id", ""),
        "transaction_type":     case.get("transaction_type", ""),
        "merchant":             case.get("merchant", ""),
        "amount":               case.get("amount", 0.0),
        "currency":             case.get("currency", "INR"),
        "dispute_reason":       case.get("dispute_reason"),
        "fraud_selected":       case.get("fraud_selected", False),
        "dispute_category":     case.get("dispute_category"),
        "fraud_suspicion":      case.get("fraud_suspicion", False),
        "priority":             case.get("priority", "MEDIUM"),
        "confidence_score":     case.get("confidence_score", 0.0),
        "risk_tags":            case.get("risk_tags", []),
        "evidence_match":       case.get("evidence_match"),
        "fallback_mode":        case.get("fallback_mode", False),
        "failure_reason":       case.get("failure_reason"),
        "status":               case.get("status", "Dispute Raised"),
        "workflow_ready":       case.get("workflow_ready", False),
        "assigned_queue":       case.get("assigned_queue"),
        "assigned_analyst":     case.get("assigned_analyst"),
        "priority_score":       case.get("priority_score", 0.0),
        "sla_deadline":         case.get("sla_deadline"),
        "sla_breached":         case.get("sla_breached", False),
        "sla_paused_at":        case.get("sla_paused_at"),
        "duplicate_of":         case.get("duplicate_of"),
        "requires_manual_review": case.get("requires_manual_review", False),
        "manual_review_reason": case.get("manual_review_reason"),
        "locked_by":            case.get("locked_by"),
        "locked_at":            case.get("locked_at"),
        "created_at":           case.get("created_at") or "",
        "updated_at":           case.get("updated_at"),
        # Omitted: investigation_plan, workflow_plan, structured_reasoning,
        #          customer_intent_summary, confidence_factors, tools_used,
        #          agent_metadata, metrics, evidence_match_note, transaction_metadata
        # These are loaded on demand in GET /cases/{case_id}
        "investigation_plan":   None,
        "workflow_plan":        None,
        # Required by Pydantic schema but empty for list view
        "email":                None,
        "phone":                None,
        "transaction_date":     None,
        "transaction_time":     None,
        "customer_comment":     None,
        "confidence_factors":   [],
        "tools_used":           [],
        "agent_metadata":       None,
        "metrics":              None,
        "evidence_match_note":  None,
        "structured_reasoning": None,
        "customer_intent_summary": None,
        # Trust Agent
        "trust_intelligence":   None,
        "user_trust_score":     case.get("user_trust_score") if case.get("user_trust_score") is not None else 1.0,
        "behavioral_risk_score": case.get("behavioral_risk_score") if case.get("behavioral_risk_score") is not None else 0.0,
        "identity_status":      case.get("identity_status") if case.get("identity_status") is not None else "PENDING",
        # Fraud Agent
        "fraud_reasoning_brief": None,
        "fraud_probability":     case.get("fraud_probability") if case.get("fraud_probability") is not None else 0.0,
        "fraud_risk_level":      case.get("fraud_risk_level") if case.get("fraud_risk_level") is not None else "LOW",
        # Evidence Agent
        "evidence_assessment":   None,
    }


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
        "confidence_factors": case.get("confidence_factors") or [],
        "tools_used": case.get("tools_used") or [],
        "agent_metadata": case.get("agent_metadata"),
        "metrics": case.get("metrics"),
        "fallback_mode": case.get("fallback_mode", False),
        "failure_reason": case.get("failure_reason"),
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
        "investigation_plan":    case.get("investigation_plan"),
        "workflow_plan":         case.get("workflow_plan"),
        "trust_intelligence":    case.get("trust_intelligence"),
        "user_trust_score":      case.get("user_trust_score") if case.get("user_trust_score") is not None else 1.0,
        "behavioral_risk_score": case.get("behavioral_risk_score") if case.get("behavioral_risk_score") is not None else 0.0,
        "identity_status":       case.get("identity_status") if case.get("identity_status") is not None else "PENDING",
        "fraud_reasoning_brief": case.get("fraud_reasoning_brief"),
        "fraud_probability":     case.get("fraud_probability") if case.get("fraud_probability") is not None else 0.0,
        "fraud_risk_level":      case.get("fraud_risk_level") if case.get("fraud_risk_level") is not None else "LOW",
        "evidence_assessment":   case.get("evidence_assessment"),
    }
