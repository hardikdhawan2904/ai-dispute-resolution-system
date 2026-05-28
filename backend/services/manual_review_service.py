"""
Manual review trigger logic.

Cases are flagged for mandatory analyst review when:
  - AI confidence < 0.55
  - ≥ 3 fraud risk indicators in risk_tags
  - Amount > 500,000 AND transaction_type == "International"
  - dispute_category == "Unauthorized Transaction" AND amount > 200,000
"""
from typing import List

_FRAUD_TAGS = {
    "POSSIBLE_FRAUD", "SUSPICIOUS_BEHAVIOR", "OTP_VERIFIED",
    "DEVICE_MISMATCH", "VELOCITY_BREACH",
}


def should_flag_manual_review(case: dict) -> tuple[bool, str]:
    """
    Returns (flag, reason).
    """
    risk_tags: List[str] = case.get("risk_tags") or []
    confidence = case.get("confidence_score") or 1.0
    amount = case.get("amount") or 0
    tx_type = case.get("transaction_type") or ""
    category = case.get("dispute_category") or ""

    fraud_hits = [t for t in risk_tags if t in _FRAUD_TAGS]

    if confidence < 0.55:
        return True, f"Low review confidence ({confidence:.0%}) — requires analyst verification"

    if len(fraud_hits) >= 3:
        return True, f"Multiple fraud indicators detected: {', '.join(fraud_hits)}"

    if amount > 500_000 and tx_type == "International":
        return True, f"High-value international transaction (₹{amount:,.0f}) requires senior review"

    if category == "Unauthorized Transaction" and amount > 200_000:
        return True, f"High-value unauthorized transaction (₹{amount:,.0f}) requires analyst sign-off"

    return False, ""
