"""
CCA — pipeline nodes.

validate_node : sanity-check inputs, stamp start time
generate_node : call LLM to produce subject + HTML body
deliver_node  : send email via SMTP, persist to communication_logs
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from agents.communication_agent.config import get_llm_config
from agents.communication_agent.state import CommunicationAgentState
from prompts.communication_prompts import SYSTEM_PROMPT, build_generation_prompt, build_html_email, NOTIFICATION_TEMPLATES
from services.email_service import send_email
from utils.helpers import extract_json_from_text
from utils.logger import agent_logger


def validate_node(state: CommunicationAgentState) -> dict:
    case_id           = (state.get("case_id") or "").strip()
    notification_type = (state.get("notification_type") or "").strip().upper()

    if not case_id:
        return {"error": "case_id is required", "status": "FAILED", "agent_start_time": time.time()}

    if not notification_type:
        return {"error": "notification_type is required", "status": "FAILED", "agent_start_time": time.time()}

    valid_types = set(NOTIFICATION_TEMPLATES.keys())
    if notification_type not in valid_types:
        notification_type = "STATUS_CHANGED"

    recipient = os.getenv("NOTIFICATION_EMAIL", state.get("case_data", {}).get("email", ""))

    return {
        "case_id":           case_id,
        "notification_type": notification_type,
        "recipient":         recipient,
        "status":            "PENDING",
        "error":             None,
        "agent_start_time":  time.time(),
    }


def generate_node(state: CommunicationAgentState) -> dict:
    if state.get("status") == "FAILED":
        return {}

    try:
        subject, body = build_html_email(
            notification_type = state.get("notification_type", "STATUS_CHANGED"),
            case_data         = state.get("case_data") or {},
            context           = state.get("context") or {},
        )
        return {"subject": subject, "body": body}

    except Exception as exc:
        agent_logger.error(f"CCA generate_node failed: {exc}", exc_info=True)
        case_id = state.get("case_id", "N/A")
        return {
            "subject": f"Dispute Update – {case_id}",
            "body":    f"<p>Dear Customer,</p><p>There is an update on your dispute case <strong>{case_id}</strong>.</p>",
            "error":   str(exc),
        }


def deliver_node(state: CommunicationAgentState) -> dict:
    if state.get("status") == "FAILED" and not state.get("subject"):
        return {"status": "FAILED"}

    subject   = state.get("subject", "")
    body      = state.get("body", "")
    recipient = state.get("recipient", "")

    sent = send_email(subject=subject, body=body, recipient=recipient)
    now  = datetime.now(timezone.utc)

    _persist_communication(state, subject, body, recipient, sent, now)

    return {
        "status":  "SENT" if sent else "FAILED",
        "sent_at": now.isoformat(),
    }


def _persist_communication(
    state: CommunicationAgentState,
    subject: str,
    body: str,
    recipient: str,
    sent: bool,
    sent_at: datetime,
) -> None:
    from database.database import SessionLocal
    from database.models import CommunicationLog

    db = SessionLocal()
    try:
        log = CommunicationLog(
            case_id           = state.get("case_id", ""),
            notification_type = state.get("notification_type", ""),
            recipient         = recipient,
            subject           = subject,
            body              = body,
            status            = "SENT" if sent else "FAILED",
            sent_at           = sent_at if sent else None,
        )
        db.add(log)
        db.commit()
        agent_logger.info(
            f"CCA: persisted communication {state.get('notification_type')} "
            f"for {state.get('case_id')} status={'SENT' if sent else 'FAILED'}"
        )
    except Exception as exc:
        agent_logger.error(f"CCA: failed to persist communication log: {exc}")
        db.rollback()
    finally:
        db.close()

