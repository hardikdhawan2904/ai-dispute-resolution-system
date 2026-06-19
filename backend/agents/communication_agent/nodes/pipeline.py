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
from prompts.communication_prompts import SYSTEM_PROMPT, build_generation_prompt, NOTIFICATION_TEMPLATES
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

    cfg = get_llm_config()
    llm = ChatGroq(
        model=cfg.get("model", "llama-3.1-8b-instant"),
        temperature=cfg.get("temperature", 0.3),
        max_tokens=cfg.get("max_tokens", 1024),
    )

    prompt = build_generation_prompt(
        notification_type = state["notification_type"],
        case_data         = state.get("case_data") or {},
        context           = state.get("context") or {},
    )

    try:
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = llm.invoke(messages)
        raw      = response.content if hasattr(response, "content") else str(response)

        parsed = extract_json_from_text(raw)
        if not parsed or "subject" not in parsed or "body" not in parsed:
            # Fallback: build a plain-text email
            case_id  = state.get("case_id", "N/A")
            n_type   = state.get("notification_type", "")
            tracking = f"http://localhost:3000/track/{case_id}"
            subject  = NOTIFICATION_TEMPLATES.get(n_type, {}).get("subject_template", "Dispute Update – {case_id}").format(case_id=case_id)
            body     = (
                f"<p>Dear Customer,</p>"
                f"<p>We are writing to update you regarding your dispute case <strong>{case_id}</strong>.</p>"
                f"<p>Please track your dispute here: <a href='{tracking}'>{tracking}</a></p>"
                f"<p>Thank you for banking with SecureBank.</p>"
            )
            return {"subject": subject, "body": body}

        return {
            "subject": parsed["subject"],
            "body":    parsed["body"],
        }

    except Exception as exc:
        agent_logger.error(f"CCA generate_node failed: {exc}", exc_info=True)
        case_id  = state.get("case_id", "N/A")
        tracking = f"http://localhost:3000/track/{case_id}"
        subject  = f"Dispute Update – {case_id}"
        body     = (
            f"<p>Dear Customer,</p>"
            f"<p>There is an update on your dispute case <strong>{case_id}</strong>. "
            f"Please track your case at: <a href='{tracking}'>{tracking}</a></p>"
            f"<p>Thank you for your patience.</p>"
        )
        return {"subject": subject, "body": body, "error": str(exc)}


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
            f"for {state.get('case_id')} → status={'SENT' if sent else 'FAILED'}"
        )
    except Exception as exc:
        agent_logger.error(f"CCA: failed to persist communication log: {exc}")
        db.rollback()
    finally:
        db.close()
