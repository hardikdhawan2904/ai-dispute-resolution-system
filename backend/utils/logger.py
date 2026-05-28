"""
Enterprise-grade structured logging for BFSI Dispute Resolution Platform.
Produces JSON-structured audit logs for compliance and traceability.
"""
import logging
import sys
import json
import traceback
from datetime import datetime, timezone
from typing import Any, Optional
from pathlib import Path


class BFSIAuditFormatter(logging.Formatter):
    """JSON-structured formatter for BFSI audit compliance."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach extra context fields
        for key in ("case_id", "customer_id", "transaction_id", "agent", "workflow_stage", "event"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        if record.exc_info:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logger(name: str, log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Configure and return an enterprise audit logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # Console handler — human-readable for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    # File handler — JSON audit logs for compliance
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(BFSIAuditFormatter())
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# ── Module-level loggers ──────────────────────────────────────────────────────

agent_logger = setup_logger("bfsi.agent", log_file="./logs/agent.log")
workflow_logger = setup_logger("bfsi.workflow", log_file="./logs/workflow.log")
api_logger = setup_logger("bfsi.api", log_file="./logs/api.log")
db_logger = setup_logger("bfsi.database", log_file="./logs/database.log")
audit_logger = setup_logger("bfsi.audit", log_file="./logs/audit.log")


def log_workflow_event(
    logger: logging.Logger,
    event: str,
    stage: str,
    case_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Emit a structured workflow audit event."""
    extra_fields = {
        "event": event,
        "workflow_stage": stage,
    }
    if case_id:
        extra_fields["case_id"] = case_id
    if customer_id:
        extra_fields["customer_id"] = customer_id
    if extra:
        extra_fields.update(extra)

    logger.info(f"[WORKFLOW] {event} @ {stage}", extra=extra_fields)
