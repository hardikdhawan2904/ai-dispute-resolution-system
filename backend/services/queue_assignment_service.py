"""
Automatic queue assignment — aligned with real Indian bank operations structure.

Queue hierarchy (ordered by priority):
  FRAUD_OPS          — all fraud / account takeover / SIM swap
  UPI_FRAUD          — UPI-specific fraud (India's largest payment channel)
  CHARGEBACK_TEAM    — credit/debit card chargebacks (PCI-DSS governed)
  ATM_INVESTIGATION  — ATM cash disputes (RBI 7-day TAT applies)
  COMPLIANCE_REVIEW  — AML/KYC flags, velocity breaches, regulatory triggers
  SENIOR_ANALYST     — high-value non-fraud cases (> ₹2L) needing senior sign-off
  MERCHANT_DISPUTES  — product/service/refund disputes with merchants
  GENERAL            — routine low-risk disputes
"""
from __future__ import annotations

from typing import List

from services.routing_rules import COMPLIANCE_TAGS as _COMPLIANCE_QUEUE_TAGS


_QUEUES = [
    "FRAUD_OPS",
    "UPI_FRAUD",
    "CHARGEBACK_TEAM",
    "ATM_INVESTIGATION",
    "COMPLIANCE_REVIEW",
    "SENIOR_ANALYST",
    "MERCHANT_DISPUTES",
    "GENERAL",
]

QUEUE_DISPLAY = {
    "FRAUD_OPS":         "Fraud Operations",
    "UPI_FRAUD":         "UPI Fraud Investigation",
    "CHARGEBACK_TEAM":   "Card Chargeback Team",
    "ATM_INVESTIGATION": "ATM Investigation",
    "COMPLIANCE_REVIEW": "Compliance & AML Review",
    "SENIOR_ANALYST":    "Senior Analyst Review",
    "MERCHANT_DISPUTES": "Merchant Disputes",
    "GENERAL":           "General Disputes",
}

# Dispute categories routed to the merchant disputes queue (non-card path)
_MERCHANT_CATEGORIES = {
    "Merchant Dispute",
    "Refund Not Received",
    "Product Not Received",
    "Subscription Abuse",
    "Duplicate Transaction",
}

# Categories that are PCI-DSS chargebacks when made via Credit/Debit Card
_CHARGEBACK_CATEGORIES = {
    "Unauthorized Transaction",
    "Duplicate Transaction",
    "Friendly Fraud",
    "Merchant Dispute",         # Card overcharge via merchant → PCI chargeback path
}


def assign_queue(case: dict) -> str:
    """Return the most appropriate queue name for this case."""
    risk_tags: List[str] = case.get("risk_tags") or []
    category   = case.get("dispute_category") or ""
    tx_type    = case.get("transaction_type") or ""
    amount     = float(case.get("amount") or 0)
    fraud_ai   = bool(case.get("fraud_suspicion"))
    fraud_cust = bool(case.get("fraud_selected"))
    fraud      = fraud_ai or fraud_cust

    # ── 1. Fraud — highest precedence ─────────────────────────────────────────
    if fraud or "POSSIBLE_FRAUD" in risk_tags:
        # UPI fraud is separated because of NPCI-specific dispute resolution process
        if tx_type in ("UPI",) and fraud:
            return "UPI_FRAUD"
        return "FRAUD_OPS"

    # ── 2. AML / regulatory signals — see services/routing_rules.py ─────────────
    if any(t in risk_tags for t in _COMPLIANCE_QUEUE_TAGS):
        # Fraud takes precedence — only route to compliance if no fraud flag
        if not fraud:
            return "COMPLIANCE_REVIEW"

    # ── 3. ATM cash issues — RBI mandated 7-day TAT ───────────────────────────
    if category == "ATM Cash Issue" or tx_type == "ATM":
        return "ATM_INVESTIGATION"

    # ── 4. Card chargebacks — PCI-DSS governed process ───────────────────────
    if tx_type in ("Credit Card", "Debit Card") and category in _CHARGEBACK_CATEGORIES:
        return "CHARGEBACK_TEAM"

    # ── 6. High-value non-fraud — senior sign-off required ────────────────────
    if amount > 200_000:   # > ₹2 lakhs
        return "SENIOR_ANALYST"

    # ── 7. Merchant / product / subscription disputes ─────────────────────────
    if category in _MERCHANT_CATEGORIES:
        return "MERCHANT_DISPUTES"

    return "GENERAL"


def all_queues() -> List[dict]:
    return [{"queue": q, "display": QUEUE_DISPLAY[q]} for q in _QUEUES]

