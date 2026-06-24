"""
Agent 6 — CCA (Customer Communication Agent)

Generates professional customer-facing email notifications for dispute
lifecycle events. Sits after the resolution pipeline and reacts to
workflow events at any stage.

Never exposes: AI terminology, fraud scores, risk signals, internal notes.
"""
from agents.communication_agent.graph import communication_graph
from agents.communication_agent.state import CommunicationAgentState
from utils.logger import agent_logger


def run_communication_agent(
    case_id: str,
    notification_type: str,
    case_data: dict,
    context: dict | None = None,
) -> dict:
    """
    Run CCA for a single notification event.

    Returns a dict with:
      subject, body, recipient, status (SENT/FAILED), sent_at, notification_type
    """
    initial: CommunicationAgentState = {
        "case_id":           case_id,
        "notification_type": notification_type,
        "case_data":         case_data,
        "context":           context or {},
        "subject":           "",
        "body":              "",
        "recipient":         "",
        "status":            "PENDING",
        "error":             None,
        "agent_start_time":  0.0,
    }

    try:
        result = communication_graph.invoke(initial, config={"recursion_limit": 6})
        return {
            "notification_type": notification_type,
            "recipient":         result.get("recipient", ""),
            "subject":           result.get("subject", ""),
            "body":              result.get("body", ""),
            "status":            result.get("status", "FAILED"),
            "sent_at":           result.get("sent_at"),
            "error":             result.get("error"),
        }
    except Exception as exc:
        agent_logger.error(f"CCA graph failed for {case_id}/{notification_type}: {exc}", exc_info=True)
        return {
            "notification_type": notification_type,
            "recipient":         "",
            "subject":           "",
            "body":              "",
            "status":            "FAILED",
            "sent_at":           None,
            "error":             str(exc),
        }

