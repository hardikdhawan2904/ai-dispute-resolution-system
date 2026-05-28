"""
Weighted priority scoring engine.

Produces a numeric priority_score (0-100) and a Priority label.
Higher score = more urgent.
"""
from typing import List


# Weight table
_W = {
    "amount_high":          25,   # > 100,000 INR
    "amount_very_high":     15,   # > 500,000 INR (stacks)
    "fraud_suspicion":      20,
    "fraud_selected":       10,
    "international":        10,
    "critical_category":    15,   # Unauthorized / ATM Cash Issue
    "high_category":        10,   # Duplicate Transaction / Refund Not Received
    "low_confidence":       10,   # AI confidence < 0.55
    "high_risk_tags":        5,   # ≥ 2 risk tags
}

_CRITICAL_CATEGORIES = {"Unauthorized Transaction", "ATM Cash Issue"}
_HIGH_CATEGORIES = {"Duplicate Transaction", "Refund Not Received"}


def compute_priority(case: dict) -> tuple[float, str]:
    """
    Returns (priority_score, priority_label).
    priority_label ∈ {CRITICAL, HIGH, MEDIUM, LOW}
    """
    score = 0.0
    amount = case.get("amount", 0) or 0
    risk_tags: List[str] = case.get("risk_tags") or []

    if amount > 100_000:
        score += _W["amount_high"]
    if amount > 500_000:
        score += _W["amount_very_high"]
    if case.get("fraud_suspicion"):
        score += _W["fraud_suspicion"]
    if case.get("fraud_selected"):
        score += _W["fraud_selected"]
    if "INTERNATIONAL_TRANSACTION" in risk_tags:
        score += _W["international"]
    if case.get("dispute_category") in _CRITICAL_CATEGORIES:
        score += _W["critical_category"]
    elif case.get("dispute_category") in _HIGH_CATEGORIES:
        score += _W["high_category"]
    if (case.get("confidence_score") or 1.0) < 0.55:
        score += _W["low_confidence"]
    if len(risk_tags) >= 2:
        score += _W["high_risk_tags"]

    score = min(score, 100.0)

    if score >= 55:
        label = "CRITICAL"
    elif score >= 35:
        label = "HIGH"
    elif score >= 15:
        label = "MEDIUM"
    else:
        label = "LOW"

    return round(score, 1), label
