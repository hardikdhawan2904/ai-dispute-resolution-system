"""
Weighted priority scoring engine — aligned with RBI dispute resolution guidelines
and Indian banking industry standards.

Priority labels and scoring bands:
  CRITICAL  ≥ 60  — immediate triage required (≤ 2 hours)
  HIGH      ≥ 35  — same-day assignment required
  MEDIUM    ≥ 15  — standard processing (2 working days)
  LOW       <  15 — routine handling (5 working days)

RBI reference:
  - RBI Circular on Limiting Customer Liability in Unauthorised Electronic Banking
    Transactions (July 2017) — zero-liability within 3 working days.
  - NPCI dispute resolution framework for UPI/IMPS.
  - PCI-DSS 4.0 chargeback SLA requirements for card transactions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

# ── Weight table ──────────────────────────────────────────────────────────────

_W = {
    # Amount tiers (INR — aligned with RBI reporting thresholds)
    "amount_above_10L":     30,   # > ₹10,00,000 — senior officer sign-off required
    "amount_above_2L":      20,   # > ₹2,00,000  — escalation threshold
    "amount_above_50K":     12,   # > ₹50,000    — heightened scrutiny
    "amount_above_10K":      5,   # > ₹10,000    — above small-transaction threshold

    # Fraud signals (RBI zero-liability rule: fraud = urgent regardless of amount)
    "fraud_confirmed":      25,   # AI + customer both say fraud
    "fraud_ai_suspected":   18,   # AI detected fraud signals
    "fraud_customer_claim": 10,   # Customer checked 'fraud' checkbox only

    # Transaction type risk (CNP and cross-border have higher chargeback rates)
    "international_txn":    12,   # INTERNATIONAL_TRANSACTION risk tag
    "card_not_present":      6,   # CNP — UPI/NetBanking/Online
    "atm_failure":           8,   # ATM issues have strict RBI TAT

    # Dispute category severity (based on RBI priority hierarchy)
    "cat_unauthorized":     15,   # Highest — RBI mandates fastest resolution
    "cat_atm_cash":         12,   # RBI: ATM disputes resolved in 7 working days
    "cat_duplicate":         8,
    "cat_refund":            6,
    "cat_product":           5,
    "cat_subscription":      4,

    # Risk tag signals
    "sim_swap":             15,   # SIM swap = account takeover risk
    "velocity_breach":      12,   # Multiple rapid transactions
    "device_mismatch":       8,   # Login from new device
    "merchant_blacklisted":  10,  # Known fraudulent merchant

    # Confidence penalty (low AI confidence → needs human)
    "low_confidence":        8,   # AI confidence < 0.60

    # Reporting delay penalty — the OPPOSITE (late reports lower urgency)
    "reported_same_day":    10,   # Reported same day → RBI zero-liability window
    "reported_within_3d":    5,   # Within 3 working days → RBI liability rules apply
}

_CAT_WEIGHTS = {
    "Unauthorized Transaction": _W["cat_unauthorized"],
    "ATM Cash Issue":           _W["cat_atm_cash"],
    "Duplicate Transaction":    _W["cat_duplicate"],
    "Refund Not Received":      _W["cat_refund"],
    "Product Not Received":     _W["cat_product"],
    "Subscription Abuse":       _W["cat_subscription"],
}

_CNP_TYPES = {"UPI", "Net Banking", "Online Purchase", "International"}


def compute_priority(case: dict) -> tuple[float, str]:
    """
    Returns (priority_score, priority_label).
    priority_label ∈ {CRITICAL, HIGH, MEDIUM, LOW}
    """
    score:    float      = 0.0
    amount:   float      = float(case.get("amount") or 0)
    risk_tags: List[str] = case.get("risk_tags") or []
    category:  str       = case.get("dispute_category") or ""
    tx_type:   str       = case.get("transaction_type") or ""
    fraud_ai   = bool(case.get("fraud_suspicion"))
    fraud_cust = bool(case.get("fraud_selected"))
    confidence = float(case.get("confidence_score") or 1.0)

    # ── Amount tiers ──────────────────────────────────────────────────────────
    if amount > 1_000_000:   # ₹10 lakhs
        score += _W["amount_above_10L"]
    elif amount > 200_000:   # ₹2 lakhs
        score += _W["amount_above_2L"]
    elif amount > 50_000:    # ₹50K
        score += _W["amount_above_50K"]
    elif amount > 10_000:    # ₹10K
        score += _W["amount_above_10K"]

    # ── Fraud signals ─────────────────────────────────────────────────────────
    if fraud_ai and fraud_cust:
        score += _W["fraud_confirmed"]
    elif fraud_ai:
        score += _W["fraud_ai_suspected"]
    elif fraud_cust:
        score += _W["fraud_customer_claim"]

    # ── Transaction type risk ─────────────────────────────────────────────────
    if "INTERNATIONAL_TRANSACTION" in risk_tags:
        score += _W["international_txn"]
    if tx_type in _CNP_TYPES:
        score += _W["card_not_present"]
    if category == "ATM Cash Issue" or tx_type == "ATM":
        score += _W["atm_failure"]

    # ── Dispute category ──────────────────────────────────────────────────────
    score += _CAT_WEIGHTS.get(category, 0)

    # ── Risk tag signals ──────────────────────────────────────────────────────
    if "SUSPICIOUS_BEHAVIOR" in risk_tags:   # covers SIM swap pattern
        score += _W["sim_swap"]
    if "VELOCITY_BREACH" in risk_tags:
        score += _W["velocity_breach"]
    if "DEVICE_MISMATCH" in risk_tags:
        score += _W["device_mismatch"]
    if "MERCHANT_BLACKLISTED" in risk_tags:
        score += _W["merchant_blacklisted"]

    # ── AI confidence ─────────────────────────────────────────────────────────
    if confidence < 0.60:
        score += _W["low_confidence"]

    # ── Reporting timeliness (RBI liability window) ───────────────────────────
    created_at = case.get("created_at") or case.get("transaction_date") or ""
    tx_date    = case.get("transaction_date") or ""
    if created_at and tx_date:
        try:
            report_dt = datetime.fromisoformat(str(created_at)).replace(tzinfo=timezone.utc)
            tx_dt     = datetime.fromisoformat(str(tx_date)).replace(tzinfo=timezone.utc)
            days_diff = (report_dt - tx_dt).days
            if days_diff <= 0:
                score += _W["reported_same_day"]
            elif days_diff <= 3:
                score += _W["reported_within_3d"]
        except (ValueError, TypeError):
            pass

    score = min(score, 100.0)

    if score >= 60:
        label = "CRITICAL"
    elif score >= 35:
        label = "HIGH"
    elif score >= 15:
        label = "MEDIUM"
    else:
        label = "LOW"

    return round(score, 1), label
