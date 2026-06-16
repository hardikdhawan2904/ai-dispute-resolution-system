"""
Ops-facing case management endpoints.

Covers: notes, document requests, locks, analyst actions, investigation timeline,
risk explanations, and advanced search.
"""
import asyncio
import pathlib
from typing import Optional
from api.executor import analysis_executor
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
from groq import RateLimitError as GroqRateLimitError
from tenacity import RetryError

from services import priority_engine, manual_review_service
from agents.dispute_agent import run_dispute_agent
from agents.investigation_agent import run_investigation_agent

router = APIRouter(prefix="/api/ops/cases", tags=["Ops — Cases"])


# ── Case notes ────────────────────────────────────────────────────────────────

@router.get("/{case_id}/notes")
async def get_notes(case_id: str, include_internal: bool = True, db: Session = Depends(get_db)):
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
async def get_document_requests(case_id: str, db: Session = Depends(get_db)):
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
async def reanalyse_case(case_id: str):
    """Re-run full Agent 1 + Agent 2 pipeline on an existing case.
    Runs the LLM call in a thread-pool executor so the async event loop
    stays free to serve other requests (e.g. listCases) during inference."""
    import re
    from database.database import SessionLocal

    # Verify case exists — Agent 1 will read full data from DB directly
    with SessionLocal() as db_read:
        if not db_read.query(DisputeCase.case_id).filter(DisputeCase.case_id == case_id).first():
            raise HTTPException(status_code=404, detail="Case not found")

    # Extract evidence text from uploaded files
    from utils.extractor import extract_text
    upload_dir = _UPLOADS_ROOT / case_id
    document_texts = []
    if upload_dir.exists():
        for f in sorted(upload_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".csv"}:
                text = extract_text(str(f))
                if text.strip():
                    document_texts.append(f"[{f.name}]\n{text}")

    def _run_analysis():
        from agents.fraud_reasoning_agent import run_fraud_reasoning_agent
        from workflows.dispute_workflow import _save_fraud_reasoning_to_db
        try:
            fraud_res = run_fraud_reasoning_agent({}, case_id=case_id)
            if fraud_res:
                _save_fraud_reasoning_to_db(case_id, fraud_res)
        except Exception as exc:
            from utils.logger import api_logger
            api_logger.warning(f"Reanalyse fraud agent failed for {case_id}: {exc}")

        # Agent 1 reads its input from DB by case_id — no manual dict needed
        return run_dispute_agent({}, case_id=case_id, document_texts=document_texts)

    try:
        result = await asyncio.get_running_loop().run_in_executor(analysis_executor, _run_analysis)
    except GroqRateLimitError as exc:
        m = re.search(r"try again in (\S+)", str(exc), re.IGNORECASE)
        wait = f" Please try again in {m.group(1)}." if m else ""
        raise HTTPException(status_code=503, detail=f"Groq API token limit exceeded.{wait}") from exc
    except RetryError as exc:
        raise HTTPException(status_code=503, detail="AI analysis service is temporarily unavailable.") from exc
    except Exception as exc:
        from utils.logger import api_logger
        api_logger.error(f"reanalyse _run_analysis failed: {type(exc).__name__}: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Analysis failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    def _save_result():
        from database.database import SessionLocal as _SL
        from workflows.dispute_workflow import _save_agent1_to_db, _save_agent2_to_db, _save_agent3_to_db
        from agents.orchestration_agent import run_orchestration_agent
        from services.queue_assignment_service import assign_queue
        from services.sla_service import compute_sla_deadline

        # Agent 1 → DB (save-first: Agent 2 reads from here)
        _save_agent1_to_db(case_id, result)

        # Agent 2 reads Agent 1 results from DB — not from in-memory dict
        try:
            inv_plan = run_investigation_agent({"case_id": case_id})
            if inv_plan:
                _save_agent2_to_db(case_id, inv_plan)
        except Exception:
            pass

        # Agent 3 reads Agent 1 + Agent 2 results from DB
        try:
            wf_plan = run_orchestration_agent(case_id)
            if wf_plan:
                _save_agent3_to_db(case_id, wf_plan)
        except Exception:
            pass

        db = _SL()
        try:
            # Re-read authoritative state after both intermediate saves
            case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
            if not case:
                return None

            from services.document_rules import resolve_investigation_status
            case.status = resolve_investigation_status(case, case_id)

            priority_score, priority_label = priority_engine.compute_priority(case.to_dict())
            case.priority_score = priority_score
            case.priority       = priority_label
            case.assigned_queue = assign_queue(case.to_dict())
            case.sla_deadline   = compute_sla_deadline(priority_label)
            flag, reason = manual_review_service.should_flag_manual_review(case.to_dict())
            case.requires_manual_review = flag
            case.manual_review_reason   = reason if flag else None

            db.add(AuditLog(
                case_id=case_id,
                event_type="REANALYSED",
                stage="structured_output",
                actor="system",
                message=f"Case re-analysed. Confidence: {case.confidence_score:.0%}, Priority: {case.priority}",
                payload={"confidence_score": case.confidence_score, "priority": case.priority},
            ))
            db.commit()
            db.refresh(case)
            return case.to_dict()
        except Exception as exc:
            from utils.logger import api_logger
            api_logger.error(f"reanalyse _save_result failed: {type(exc).__name__}: {exc}", exc_info=True)
            db.rollback()
            raise
        finally:
            db.close()

    try:
        final = await asyncio.get_running_loop().run_in_executor(analysis_executor, _save_result)
    except Exception as exc:
        from utils.logger import api_logger
        api_logger.error(f"reanalyse _save_result executor failed: {type(exc).__name__}: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Save failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    if final is None:
        raise HTTPException(status_code=404, detail="Case not found after analysis")
    return final


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
async def analyse_uploads(case_id: str):
    """Re-run unified analysis on all uploaded files for a case.
    Runs the LLM call in a thread-pool executor so the async event loop
    stays free to serve other requests during inference."""
    from agents.dispute_agent import run_dispute_agent
    from utils.extractor import extract_text
    from database.database import SessionLocal

    # Verify case exists — Agent 1 reads full data from DB by case_id
    with SessionLocal() as db_read:
        if not db_read.query(DisputeCase.case_id).filter(DisputeCase.case_id == case_id).first():
            raise HTTPException(status_code=404, detail="Case not found")

    case_dir = _UPLOADS_ROOT / case_id
    if not case_dir.exists():
        return {"case_id": case_id, "analysed": 0, "files": []}

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

    if not document_texts:
        files = [
            {"name": f.name, "url": f"/uploads/{case_id}/{f.name}", "is_image": f.suffix.lower() in _IMAGE_EXTS}
            for f in sorted(case_dir.iterdir()) if f.is_file()
        ]
        return {"case_id": case_id, "analysed": 0, "files": files}

    def _run_analysis():
        from agents.fraud_reasoning_agent import run_fraud_reasoning_agent
        from workflows.dispute_workflow import _save_fraud_reasoning_to_db
        try:
            fraud_res = run_fraud_reasoning_agent({}, case_id=case_id)
            if fraud_res:
                _save_fraud_reasoning_to_db(case_id, fraud_res)
        except Exception as exc:
            from utils.logger import api_logger
            api_logger.warning(f"Analyse uploads fraud agent failed for {case_id}: {exc}")

        # Agent 1 reads its input from DB by case_id
        return run_dispute_agent({}, case_id=case_id, document_texts=document_texts)

    try:
        result = await asyncio.get_running_loop().run_in_executor(analysis_executor, _run_analysis)
    except GroqRateLimitError as exc:
        raise HTTPException(status_code=503, detail="Groq API token limit exceeded.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {type(exc).__name__}") from exc

    def _save_result():
        from database.database import SessionLocal as _SL
        from workflows.dispute_workflow import _save_agent1_to_db, _save_agent2_to_db, _save_agent3_to_db
        from agents.investigation_agent import run_investigation_agent as _run_inv
        from agents.orchestration_agent import run_orchestration_agent as _run_woa
        from services.priority_engine import compute_priority as _cp
        from services.queue_assignment_service import assign_queue as _aq
        from services.sla_service import compute_sla_deadline as _sla
        from services.manual_review_service import should_flag_manual_review as _mr

        # Agent 1 → DB (save-first)
        _save_agent1_to_db(case_id, result)

        # Agent 2 reads Agent 1 results from DB
        try:
            inv_plan = _run_inv({"case_id": case_id})
            if inv_plan:
                _save_agent2_to_db(case_id, inv_plan)
        except Exception:
            pass

        # Agent 3 reads Agent 1 + Agent 2 results from DB
        try:
            wf_plan = _run_woa(case_id)
            if wf_plan:
                _save_agent3_to_db(case_id, wf_plan)
        except Exception:
            pass

        db = _SL()
        try:
            # Re-read authoritative state after both intermediate saves
            case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
            if not case:
                return None

            from services.document_rules import resolve_investigation_status
            case.status = resolve_investigation_status(case, case_id)

            # Recompute priority, queue, SLA on the fresh DB state
            priority_score, priority_label = _cp(case.to_dict())
            case.priority_score = priority_score
            case.priority       = priority_label
            case.assigned_queue = _aq(case.to_dict())
            case.sla_deadline   = _sla(priority_label)
            flag, reason = _mr(case.to_dict())
            case.requires_manual_review = flag
            case.manual_review_reason   = reason if flag else None

            db.add(AuditLog(
                case_id=case_id,
                event_type="REANALYSED",
                actor="system",
                message=f"Unified re-analysis with {len(document_texts)} document(s). Confidence: {case.confidence_score:.0%}",
                payload={
                    "documents_extracted": len(document_texts),
                    "confidence_score":    case.confidence_score,
                    "priority":            case.priority,
                },
            ))
            db.commit()
            db.refresh(case)
            return {
                "case_id":  case_id,
                "analysed": analysed,
                "files": [
                    {"name": f.name, "url": f"/uploads/{case_id}/{f.name}", "is_image": f.suffix.lower() in _IMAGE_EXTS}
                    for f in sorted(case_dir.iterdir()) if f.is_file()
                ],
            }
        finally:
            db.close()

    response = await asyncio.get_running_loop().run_in_executor(analysis_executor, _save_result)
    if response is None:
        raise HTTPException(status_code=404, detail="Case not found after analysis")
    return response


# ── Advanced search ───────────────────────────────────────────────────────────

@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    for model in [AuditLog, WorkflowState, CaseNote, DocumentRequest]:
        db.query(model).filter(model.case_id == case_id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()


# ── Evidence assessment (Agent 4 — EIA) ──────────────────────────────────────

@router.get("/{case_id}/evidence-assessment")
def get_evidence_assessment(case_id: str, db: Session = Depends(get_db)):
    """Return the stored evidence assessment from Agent 4 (EIA) for a case."""
    case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {
        "case_id":            case_id,
        "evidence_assessment": getattr(case, "evidence_assessment", None),
    }


@router.post("/{case_id}/run-evidence-agent")
async def run_evidence_agent_endpoint(case_id: str):
    """
    Manually trigger Agent 4 (EIA) for an existing case.
    Runs in a thread-pool executor so the event loop stays free during inference.
    """
    from database.database import SessionLocal as _SL
    from workflows.dispute_workflow import _save_evidence_to_db
    from agents.evidence_agent import run_evidence_agent as _run_eia

    # Verify case exists
    with _SL() as db_read:
        case_row = db_read.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")
        workflow_plan = case_row.workflow_plan

    def _run():
        return _run_eia(case_id)

    try:
        evidence_assessment = await asyncio.get_running_loop().run_in_executor(
            analysis_executor, _run
        )
    except GroqRateLimitError as exc:
        raise HTTPException(status_code=503, detail="Groq API token limit exceeded.") from exc
    except RetryError as exc:
        raise HTTPException(status_code=503, detail="AI evidence service temporarily unavailable.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Evidence agent failed: {type(exc).__name__}: {str(exc)[:300]}") from exc

    # Save evidence assessment and update workflow plan
    _save_evidence_to_db(case_id, evidence_assessment, workflow_plan or {})

    # Fetch updated case for response
    with _SL() as db_read:
        case_row = db_read.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        return {
            "case_id":            case_id,
            "evidence_assessment": evidence_assessment,
            "case":               case_row.to_dict() if case_row else None,
        }


@router.post("/search")
async def search_cases(body: CaseSearchRequest, db: Session = Depends(get_db)):
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
