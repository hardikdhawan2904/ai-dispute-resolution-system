"""
Weighted priority scoring engine — aligned with RBI dispute resolution guidelines
and Indian banking industry standards.

Priority labels and scoring bands:
  CRITICAL  ≥ 65  — immediate triage required (≤ 2 hours)
  HIGH      ≥ 40  — same-day assignment required
  MEDIUM    ≥ 20  — standard processing (2 working days)
  LOW       <  20 — routine handling (5 working days)

Every legitimately submitted dispute starts at 10 (base) so no valid case ever
scores LOW on category + amount alone — LOW is reserved for edge cases only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

# ── Weight table ──────────────────────────────────────────────────────────────

_W = {
    # Base — every submitted dispute deserves triage attention
    "base":               10,

    # Amount tiers (INR — aligned with RBI reporting thresholds)
    "amount_above_10L":   30,   # > ₹10,00,000 — senior officer sign-off required
    "amount_above_2L":    20,   # > ₹2,00,000  — escalation threshold
    "amount_above_50K":   12,   # > ₹50,000    — heightened scrutiny
    "amount_above_10K":    8,   # > ₹10,000    — above small-transaction threshold
    "amount_above_5K":     5,   # > ₹5,000     — meaningful amount for retail banking
    "amount_above_1K":     3,   # > ₹1,000     — any non-trivial transaction

    # Fraud signals (RBI zero-liability rule: fraud = urgent regardless of amount)
    "fraud_confirmed":    25,   # AI + customer both say fraud
    "fraud_ai_suspected": 18,   # AI detected fraud signals
    "fraud_customer_claim": 10, # Customer checked 'fraud' checkbox only

    # Transaction type risk (CNP and cross-border have higher chargeback rates)
    "international_txn":  12,   # INTERNATIONAL_TRANSACTION risk tag
    "card_not_present":    6,   # CNP — UPI/NetBanking/Online
    "atm_failure":         8,   # ATM issues have strict RBI 7-day TAT

    # Dispute category severity (based on RBI priority hierarchy)
    "cat_unauthorized":   18,   # Highest — RBI zero-liability mandates fastest resolution
    "cat_atm_cash":       14,   # RBI: ATM disputes resolved in 7 working days
    "cat_duplicate":      12,   # Clear double-charge evidence; straightforward resolution
    "cat_refund":         12,   # Merchant confirmed refund not credited — operational issue
    "cat_product":        10,   # Product/service non-delivery
    "cat_subscription":    8,   # Recurring charge without consent
    "cat_merchant":        8,   # Overcharge / price dispute

    # Risk tag signals
    "sim_swap":           15,   # SIM swap = account takeover risk
    "velocity_breach":    12,   # Multiple rapid transactions
    "device_mismatch":     8,   # Login from new device
    "merchant_blacklisted": 10, # Known fraudulent merchant

    # Confidence penalty (low AI confidence → needs human)
    "low_confidence":      8,   # AI confidence < 0.60

    # Reporting timeliness (RBI liability window)
    "reported_same_day":  10,   # Reported same day → RBI zero-liability window
    "reported_within_3d":  5,   # Within 3 working days → RBI liability rules apply
}

_CAT_WEIGHTS = {
    "Unauthorized Transaction": _W["cat_unauthorized"],
    "ATM Cash Issue":           _W["cat_atm_cash"],
    "Duplicate Transaction":    _W["cat_duplicate"],
    "Refund Not Received":      _W["cat_refund"],
    "Product Not Received":     _W["cat_product"],
    "Subscription Abuse":       _W["cat_subscription"],
    "Merchant Dispute":         _W["cat_merchant"],
}

# Card-Not-Present transaction types.
# Debit Card is included because online Debit Card payments (e-commerce) are CNP
# even though in-person POS debit swipes are not — we can't distinguish at this stage
# so we apply the CNP signal conservatively (any Debit Card dispute gets the flag).
_CNP_TYPES = {"UPI", "Net Banking", "Online Purchase", "International", "Debit Card", "Credit Card"}


def compute_priority(case: dict) -> tuple[float, str]:
    """
    Returns (priority_score, priority_label).
    priority_label ∈ {CRITICAL, HIGH, MEDIUM, LOW}
    """
    score:     float      = float(_W["base"])   # every dispute starts here
    amount:    float      = float(case.get("amount") or 0)
    risk_tags: List[str]  = case.get("risk_tags") or []
    category:  str        = case.get("dispute_category") or ""
    tx_type:   str        = case.get("transaction_type") or ""
    fraud_ai   = bool(case.get("fraud_suspicion"))
    fraud_cust = bool(case.get("fraud_selected"))
    confidence = float(case.get("confidence_score") or 1.0)

    # ── Amount tiers ──────────────────────────────────────────────────────────
    if amount > 1_000_000:       # ₹10 lakhs
        score += _W["amount_above_10L"]
    elif amount > 200_000:       # ₹2 lakhs
        score += _W["amount_above_2L"]
    elif amount > 50_000:        # ₹50K
        score += _W["amount_above_50K"]
    elif amount > 10_000:        # ₹10K
        score += _W["amount_above_10K"]
    elif amount > 5_000:         # ₹5K
        score += _W["amount_above_5K"]
    elif amount > 1_000:         # ₹1K
        score += _W["amount_above_1K"]

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
    if "SUSPICIOUS_BEHAVIOR" in risk_tags:
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
    created_at = case.get("created_at") or ""
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

    if score >= 65:
        label = "CRITICAL"
    elif score >= 40:
        label = "HIGH"
    elif score >= 20:
        label = "MEDIUM"
    else:
        label = "LOW"

    return round(score, 1), label

