"""
Agent 1 (ARIA) fallback service — generates a safe, minimal case analysis when the
LLM is completely unavailable (Groq outage, rate limit, network failure, timeout, etc.).

Guarantees that customer disputes are NEVER lost due to AI service failures.
All activations are fully auditable: failure reason, timestamp, and retry count
are embedded in the returned output dict.
"""
from __future__ import annotations

from utils.helpers import utc_now_iso
from utils.logger import agent_logger

# ── Failure reason constants ──────────────────────────────────────────────────

RATE_LIMIT        = "RATE_LIMIT"
TIMEOUT           = "TIMEOUT"
NETWORK_ERROR     = "NETWORK_ERROR"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
JSON_PARSE_ERROR  = "JSON_PARSE_ERROR"
TOOL_FAILURE      = "TOOL_FAILURE"
UNKNOWN_ERROR     = "UNKNOWN_ERROR"


# ── Failure classifier ────────────────────────────────────────────────────────

def classify_failure(exc: Exception) -> str:
    """Map any exception raised by Agent 1 to a structured failure reason code."""
    try:
        from groq import RateLimitError as GroqRateLimitError
        if isinstance(exc, GroqRateLimitError):
            return RATE_LIMIT
    except ImportError:
        pass

    exc_str  = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    if isinstance(exc, TimeoutError) or "timeout" in exc_str or "timed out" in exc_str:
        return TIMEOUT

    if isinstance(exc, (ConnectionError, OSError)):
        return NETWORK_ERROR

    if "rate limit" in exc_str or "rate_limit" in exc_str or "429" in exc_str or "too many requests" in exc_str:
        return RATE_LIMIT

    if "connection" in exc_str or "network" in exc_str or "unreachable" in exc_str:
        return NETWORK_ERROR

    if "model" in exc_str and (
        "unavailable" in exc_str or "not found" in exc_str
        or "invalid" in exc_str or "does not exist" in exc_str
        or "decommissioned" in exc_str
    ):
        return MODEL_UNAVAILABLE

    return UNKNOWN_ERROR


# ── Fallback generator ────────────────────────────────────────────────────────

def generate_agent1_fallback(
    dispute_input: dict,
    failure_reason: str,
    retry_count: int = 3,
    duration_ms: float = 0.0,
) -> dict:
    """
    Return a structurally complete Agent 1 output dict when ARIA cannot execute.

    The returned dict is identical in shape to a normal ARIA output so that:
      - priority_engine, queue_assignment, SLA, and Agent 2 run unchanged
      - persistence writes to all expected columns without errors
      - the frontend can detect fallback_mode=True and show the appropriate warning

    Args:
        dispute_input:  Raw intake form dict (already validated upstream).
        failure_reason: One of the REASON constants above.
        retry_count:    How many LLM retries were exhausted before giving up.
        duration_ms:    Wall-clock time consumed before fallback fired.
    """
    case_id            = dispute_input.get("case_id") or dispute_input.get("_preset_case_id") or ""
    fraud              = bool(dispute_input.get("fraud_selected", False))
    fallback_timestamp = utc_now_iso()

    agent_logger.error(
        "AGENT1_FALLBACK_ACTIVATED — LLM unavailable, returning safe fallback",
        extra={
            "case_id":        case_id,
            "failure_reason": failure_reason,
            "retry_count":    retry_count,
            "duration_ms":    duration_ms,
        },
    )

    return {
        # ── Core classification (safe defaults) ───────────────────────────────
        "case_id":                 case_id,
        "customer_id":             dispute_input.get("customer_id", ""),
        "transaction_id":          dispute_input.get("transaction_id", ""),
        "transaction_type":        dispute_input.get("transaction_type", ""),
        "merchant":                dispute_input.get("merchant", ""),
        "amount":                  float(dispute_input.get("amount", 0)),
        "currency":                dispute_input.get("currency", "INR"),
        "dispute_category":        "Other",
        "fraud_suspicion":         fraud,
        "customer_intent_summary": (
            "Automated analysis was unavailable when this case was submitted. "
            "A fallback record has been created — manual review is required."
        ),
        "confidence_score":        0.10,
        "confidence_factors":      [f"LLM service unavailable — failure: {failure_reason}"],
        "risk_tags":               _build_risk_tags(fraud),
        "structured_reasoning":    (
            f"Agent 1 (ARIA) fallback mode activated. "
            f"Failure reason: {failure_reason}. "
            "This case could not be automatically classified and requires manual investigation."
        ),
        "evidence_match":          None,
        "evidence_match_note":     "",
        "status":                  "Dispute Raised",
        "workflow_ready":          True,

        # ── Fallback identification flags (Changes 3 & 4) ─────────────────────
        "fallback_mode":   True,
        "failure_reason":  failure_reason,

        # ── Audit trail (Changes 7 & 11) ──────────────────────────────────────
        "tools_used": [],
        "agent_metadata": {
            "name":        "ARIA",
            "version":     "1.0",
            "model":       "N/A — fallback mode",
            "timestamp":   fallback_timestamp,
            "duration_ms": duration_ms,
        },
        "metrics": {
            "total_duration_ms":  duration_ms,
            "llm_calls":          0,
            "tool_calls":         0,
            "retry_count":        retry_count,
            "fallback_activated": True,
            "failure_reason":     failure_reason,
            "fallback_timestamp": fallback_timestamp,
        },
        "created_at": fallback_timestamp,
    }


def _build_risk_tags(fraud: bool) -> list:
    tags = ["AI_UNAVAILABLE", "HIGH_PRIORITY_CASE"]
    if fraud:
        tags.append("POSSIBLE_FRAUD")
    return tags

