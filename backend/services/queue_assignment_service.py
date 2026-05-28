"""
Automatic queue assignment based on case attributes.

Queues:
  FRAUD_OPS          — confirmed or suspected fraud
  ATM_INVESTIGATION  — ATM cash issues
  CHARGEBACK_TEAM    — credit card chargebacks
  COMPLIANCE_REVIEW  — regulatory / AML flags
  HIGH_PRIORITY      — CRITICAL priority non-fraud
  GENERAL            — default
"""
from typing import List


_QUEUES = [
    "FRAUD_OPS",
    "ATM_INVESTIGATION",
    "CHARGEBACK_TEAM",
    "COMPLIANCE_REVIEW",
    "HIGH_PRIORITY",
    "GENERAL",
]

QUEUE_DISPLAY = {
    "FRAUD_OPS":         "Fraud Operations",
    "ATM_INVESTIGATION": "ATM Investigation",
    "CHARGEBACK_TEAM":   "Chargeback Team",
    "COMPLIANCE_REVIEW": "Compliance Review",
    "HIGH_PRIORITY":     "High Priority",
    "GENERAL":           "General",
}


def assign_queue(case: dict) -> str:
    """Return the queue name for this case."""
    risk_tags: List[str] = case.get("risk_tags") or []
    category   = case.get("dispute_category", "") or ""
    tx_type    = case.get("transaction_type", "") or ""
    priority   = case.get("priority", "MEDIUM")
    fraud_flag = case.get("fraud_suspicion", False)

    if fraud_flag or "POSSIBLE_FRAUD" in risk_tags or "SUSPICIOUS_BEHAVIOR" in risk_tags:
        return "FRAUD_OPS"

    if "ATM Cash Issue" in category or tx_type == "ATM":
        return "ATM_INVESTIGATION"

    if tx_type in ("Credit Card",) and category in ("Unauthorized Transaction", "Duplicate Transaction"):
        return "CHARGEBACK_TEAM"

    if "VELOCITY_BREACH" in risk_tags or "SIM_SWAP" in risk_tags:
        return "COMPLIANCE_REVIEW"

    if priority == "CRITICAL":
        return "HIGH_PRIORITY"

    return "GENERAL"


def all_queues() -> List[dict]:
    return [{"queue": q, "display": QUEUE_DISPLAY[q]} for q in _QUEUES]
