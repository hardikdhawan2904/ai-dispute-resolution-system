"""
Human-readable risk explanations for the ops dashboard.

Maps risk_tags and case attributes → plain English explanations for analysts.
Terminology uses banking operations language, not AI/ML jargon.
"""
from typing import List

_TAG_EXPLANATIONS = {
    "HIGH_VALUE_TRANSACTION":    "Transaction value exceeds ₹1,00,000 — requires additional scrutiny per policy.",
    "INTERNATIONAL_TRANSACTION": "Transaction originated from or was directed to an international account.",
    "POSSIBLE_FRAUD":            "Transaction pattern matches known fraud signatures in our detection models.",
    "DUPLICATE_PAYMENT":         "A similar transaction was detected within a short time window for this account.",
    "FRIENDLY_FRAUD_RISK":       "Customer history or behaviour may indicate an illegitimate chargeback attempt.",
    "HIGH_PRIORITY_CASE":        "Case has been escalated to high priority based on risk assessment.",
    "OTP_VERIFIED":              "Customer may have shared OTP with a third party — social engineering suspected.",
    "DEVICE_MISMATCH":           "Transaction device does not match the customer's registered devices.",
    "SUSPICIOUS_BEHAVIOR":       "Unusual account activity detected around the time of this transaction.",
    "CARD_NOT_PRESENT":          "Transaction was conducted without physical card — higher fraud risk.",
    "RECURRING_DISPUTE":         "Customer has filed multiple disputes — pattern warrants closer review.",
    "MERCHANT_BLACKLISTED":      "Merchant appears on internal or network watchlist.",
    "VELOCITY_BREACH":           "Transaction frequency exceeded normal thresholds in a short period.",
}


def explain_risk(case: dict) -> List[dict]:
    """
    Returns a list of {tag, explanation} dicts for each risk tag on the case.
    """
    risk_tags: List[str] = case.get("risk_tags") or []
    result = []
    for tag in risk_tags:
        if tag in _TAG_EXPLANATIONS:
            result.append({"tag": tag, "explanation": _TAG_EXPLANATIONS[tag]})
        else:
            result.append({"tag": tag, "explanation": f"Risk indicator: {tag.replace('_', ' ').title()}"})
    return result


def get_investigation_summary(case: dict) -> str:
    """
    Returns a plain-English investigation summary replacing raw AI output.
    """
    summary = case.get("customer_intent_summary") or ""
    category = case.get("dispute_category") or ""
    confidence = case.get("confidence_score") or 0.0
    manual = case.get("requires_manual_review", False)

    confidence_label = (
        "High" if confidence >= 0.75
        else "Moderate" if confidence >= 0.55
        else "Low"
    )

    parts = []
    if category:
        parts.append(f"Dispute classified as: {category}.")
    if summary:
        parts.append(summary)
    parts.append(f"Review confidence: {confidence_label} ({confidence:.0%}).")
    if manual:
        parts.append("This case requires mandatory analyst review before resolution.")

    return " ".join(parts)
