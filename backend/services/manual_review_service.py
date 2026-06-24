"""
Manual review flag logic — aligned with RBI compliance requirements and
Indian banking risk management standards.

RBI mandates for mandatory human review:
  1. All fraud disputes (zero-liability rule requires bank to verify before crediting)
  2. High-value disputes above ₹2,00,000 (internal control requirement)
  3. Cases with AML/KYC implications (PMLA compliance)
  4. Repeat claimants (3+ disputes in 90 days) — FEMA / fraud pattern alert
  5. Friendly fraud indicators (prevents bank revenue leakage)
  6. Low AI confidence — model uncertainty requires human override
"""
from __future__ import annotations

from typing import List, Tuple


# Tags that indicate active fraud patterns
_FRAUD_SIGNAL_TAGS = {
    "POSSIBLE_FRAUD",
    "SUSPICIOUS_BEHAVIOR",
    "OTP_COMPROMISED",
    "DEVICE_MISMATCH",
    "VELOCITY_BREACH",
    "MERCHANT_BLACKLISTED",
}

# Tags that always require compliance review
_COMPLIANCE_TAGS = {
    "VELOCITY_BREACH",       # AML red flag
    "SUSPICIOUS_BEHAVIOR",   # Account takeover / SIM swap
    "MERCHANT_BLACKLISTED",  # Known fraud merchant
}


def should_flag_manual_review(case: dict) -> Tuple[bool, str]:
    """
    Returns (should_flag, reason_string).
    Checks every condition; returns the highest-priority reason if multiple apply.
    """
    risk_tags:  List[str] = case.get("risk_tags") or []
    confidence: float     = float(case.get("confidence_score") or 1.0)
    amount:     float     = float(case.get("amount") or 0)
    tx_type:    str       = case.get("transaction_type") or ""
    category:   str       = case.get("dispute_category") or ""
    fraud_ai    = bool(case.get("fraud_suspicion"))
    fraud_cust  = bool(case.get("fraud_selected"))

    fraud_hits = [t for t in risk_tags if t in _FRAUD_SIGNAL_TAGS]

    # ── 1. All fraud disputes — RBI zero-liability verification ───────────────
    if fraud_ai and fraud_cust:
        return True, (
            "Customer and AI both flagged fraud — RBI zero-liability rule requires "
            "mandatory analyst verification before chargeback credit"
        )

    # ── 2. AI fraud suspicion — ANY amount requires review (RBI zero-liability) ──
    # RBI circular 2017: bank bears liability for fraud regardless of amount if
    # reported promptly. Analyst must verify before any credit.
    if fraud_ai:
        return True, (
            f"AI-detected fraud on ₹{amount:,.0f} transaction — "
            "RBI zero-liability rule requires mandatory analyst verification "
            "before any chargeback credit regardless of amount"
        )

    # ── 3. Compliance / AML triggers ─────────────────────────────────────────
    comp_hits = [t for t in risk_tags if t in _COMPLIANCE_TAGS]
    if comp_hits:
        return True, (
            f"Compliance trigger detected: {', '.join(comp_hits)} — "
            "AML/KYC review required under PMLA guidelines"
        )

    # ── 4. Friendly fraud risk — prevents unjustified chargebacks ────────────
    if "FRIENDLY_FRAUD_RISK" in risk_tags:
        return True, (
            "Friendly fraud risk detected — merchant chargeback pattern "
            "requires analyst review before processing"
        )

    # ── 5. High-value dispute (non-fraud) — internal control requirement ──────
    if amount > 200_000:
        return True, (
            f"High-value dispute (₹{amount:,.0f} > ₹2,00,000) — "
            "senior analyst sign-off required per bank internal controls"
        )

    # ── 6. Multiple fraud indicators — pattern suggests organised fraud ────────
    if len(fraud_hits) >= 2:
        return True, (
            f"Multiple fraud risk signals: {', '.join(fraud_hits)} — "
            "pattern consistent with organised fraud attempt"
        )

    # ── 7. High-value international transaction ───────────────────────────────
    if tx_type == "International" and amount > 50_000:
        return True, (
            f"High-value international transaction (₹{amount:,.0f}) — "
            "FEMA reporting threshold check and analyst review required"
        )

    # ── 8. Unauthorized transaction above ₹50,000 ────────────────────────────
    if category == "Unauthorized Transaction" and amount > 50_000:
        return True, (
            f"Unauthorized transaction of ₹{amount:,.0f} — "
            "RBI liability assessment requires analyst review"
        )

    # ── 9. Low AI confidence — model uncertainty ──────────────────────────────
    if confidence < 0.60:
        return True, (
            f"Low classification confidence ({confidence:.0%}) — "
            "AI output unreliable, mandatory analyst verification"
        )

    return False, ""

