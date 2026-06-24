"""
Communication service — bridges workflow events to CCA (Agent 6).

trigger_communication() is the single entry point.  Call it from anywhere
in the workflow (dispute_service, dispute_workflow) wrapped in try/except
so CCA failures never affect the main dispute pipeline.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from utils.logger import api_logger


def trigger_communication(
    case_id: str,
    notification_type: str,
    db: Session,
    context: dict | None = None,
) -> dict | None:
    """
    Fetch case, run CCA, persist to communication_logs, return log dict.
    Returns None on any failure — never raises.
    """
    try:
        from database.models import DisputeCase, CommunicationLog
        from agents.communication_agent import run_communication_agent

        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            api_logger.warning(f"communication_service: case {case_id} not found")
            return None

        # Deduplicate: every auto-triggered type fires at most once per case.
        # Manual sends via + Send Update button pass _skip_dedup=True to override.
        _ONE_SHOT_TYPES = {
            "CASE_RECEIVED",
            "INVESTIGATION_STARTED",
            "FRAUD_REVIEW_STARTED",
            "EVIDENCE_REVIEW_COMPLETED",
            "DOCUMENT_REQUESTED",
            "CASE_RESOLVED",
        }
        skip_dedup = (context or {}).get("_skip_dedup", False)
        if notification_type in _ONE_SHOT_TYPES and not skip_dedup:
            already = (
                db.query(CommunicationLog)
                .filter(
                    CommunicationLog.case_id == case_id,
                    CommunicationLog.notification_type == notification_type,
                )
                .first()
            )
            if already:
                api_logger.info(
                    f"communication_service: skipping duplicate {notification_type} for {case_id}"
                )
                return None

        # Build customer-safe subset — no fraud scores, risk signals, or internal details
        case_data = {
            "case_id":          case.case_id,
            "customer_name":    case.customer_name or "Valued Customer",
            "email":            case.email or "",
            "amount":           float(case.amount or 0),
            "currency":         case.currency or "INR",
            "merchant":         case.merchant or "",
            "transaction_type": case.transaction_type or "",
            "status":           case.status or "Under Review",
            "dispute_category": case.dispute_category or "",
        }

        result = run_communication_agent(
            case_id           = case_id,
            notification_type = notification_type,
            case_data         = case_data,
            context           = context or {},
        )

        # Persist — but only if not already persisted by the deliver_node
        # (deliver_node persists internally; this is a safety net if graph failed before deliver)
        if result.get("status") == "FAILED" and result.get("subject"):
            try:
                log = CommunicationLog(
                    case_id           = case_id,
                    notification_type = notification_type,
                    recipient         = result.get("recipient", ""),
                    subject           = result.get("subject", ""),
                    body              = result.get("body", ""),
                    status            = "FAILED",
                    sent_at           = None,
                )
                db.add(log)
                db.commit()
            except Exception:
                pass

        return result

    except Exception as exc:
        api_logger.error(
            f"communication_service: trigger_communication failed for {case_id}/{notification_type}: {exc}",
            exc_info=True,
        )
        return None


def trigger_communication_async(
    case_id: str,
    notification_type: str,
    context: dict | None = None,
) -> None:
    """
    Fire-and-forget version — runs CCA in a background thread.
    Use this from workflow nodes so the main pipeline is never blocked.
    """
    def _run():
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            trigger_communication(case_id, notification_type, db, context)
        except Exception as exc:
            api_logger.error(f"async communication trigger failed: {exc}")
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

