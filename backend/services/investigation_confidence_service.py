"""
Investigation Confidence Service — deterministic, no LLM.

Computes a single investigation_confidence score (0.10–1.00) measuring how
reliable the full investigation plan is, distinct from:
  - Agent 1 confidence_score  (dispute classification accuracy)
  - queue_confidence           (routing certainty)
  - data_quality_score         (raw input completeness)

Weighting model (total = 100%):
  35%  queue_confidence          — routing decision certainty
  30%  data_quality_score        — investigation data completeness
  20%  historical precedent      — resolution statistics for this category
  10%  fraud signal consistency  — fraud indicators vs. category alignment
   5%  coverage breadth          — how many tools returned useful data

BFSI standard: investigations scoring below 0.60 are flagged for mandatory
human review before any resolution recommendation is made.
"""
from __future__ import annotations


def calculate_investigation_confidence(plan: dict) -> float:
    queue_conf    = float(plan.get("queue_confidence")   or 0.50)
    data_quality  = float(plan.get("data_quality_score") or 0.50)
    similarity    = _historical_precedent_score(plan.get("related_cases") or {})
    fraud_align   = _fraud_signal_alignment(plan)
    coverage      = _coverage_score(plan.get("investigation_coverage") or {})

    score = (
        0.35 * queue_conf  +
        0.30 * data_quality +
        0.20 * similarity   +
        0.10 * fraud_align  +
        0.05 * coverage
    )
    return round(max(0.10, min(1.00, score)), 2)


def calculate_confidence_tier(score: float) -> str:
    """Map numeric score to BFSI confidence tier label."""
    if score >= 0.85:
        return "Very High — automated processing appropriate"
    if score >= 0.70:
        return "High — standard analyst review sufficient"
    if score >= 0.55:
        return "Moderate — analyst verification recommended"
    return "Low — mandatory human review required"


def generate_confidence_factors(plan: dict) -> list:
    factors: list[str] = []

    # Historical precedent
    related  = plan.get("related_cases") or {}
    similar  = int(related.get("similar_cases") or 0)
    res_rate = float(related.get("resolution_rate") or 0.0)

    if similar >= 10:
        factors.append(
            f"Strong historical precedent ({similar} cases, {res_rate:.0%} resolution rate) "
            "— reliable outcome prediction"
        )
    elif similar >= 3:
        factors.append(
            f"Moderate historical precedent ({similar} cases) — "
            "some outcome guidance available"
        )
    elif similar >= 1:
        factors.append("Limited historical precedent — analyst should treat as novel case")
    else:
        factors.append("No historical precedent found — outcome highly uncertain")

    # Merchant profile
    merch = plan.get("merchant_risk_profile") or {}
    m_risk = merch.get("merchant_risk", "")
    if m_risk == "CRITICAL":
        factors.append("Merchant has CRITICAL risk level — multiple prior complaints / blacklist pattern")
    elif m_risk == "HIGH":
        factors.append("Merchant has HIGH risk level — elevated complaint history")
    elif m_risk in ("LOW", "MEDIUM") and m_risk:
        factors.append(f"Merchant profile available (risk: {m_risk})")

    # Customer dispute history
    cust = plan.get("customer_risk_profile") or {}
    prior = cust.get("previous_disputes")
    fraud_claims = cust.get("fraud_claims") or 0
    if prior is not None:
        if prior >= 5:
            factors.append(
                f"Customer has {prior} prior disputes ({fraud_claims} fraud claims) — "
                "elevated repeat-claimant risk"
            )
        elif prior >= 2:
            factors.append(f"Customer has {prior} prior disputes — moderate repeat-dispute pattern")
        else:
            factors.append("First-time or infrequent disputer — lower misuse risk")

    # Data quality
    dq = float(plan.get("data_quality_score") or 0)
    if dq >= 0.90:
        factors.append(f"Excellent investigation data quality ({dq:.0%}) — all sources returned complete data")
    elif dq >= 0.75:
        factors.append(f"Good investigation data quality ({dq:.0%})")
    elif dq >= 0.60:
        factors.append(f"Moderate data quality ({dq:.0%}) — some gaps in investigation data")
    else:
        factors.append(f"Limited data quality ({dq:.0%}) — significant investigation gaps")

    # Queue routing confidence
    qc = float(plan.get("queue_confidence") or 0)
    if qc >= 0.90:
        factors.append("High routing confidence — clear queue assignment")
    elif qc < 0.65:
        factors.append("Low routing confidence — queue assignment may need analyst override")

    # Duplicate detection result
    if plan.get("duplicate_found"):
        factors.append(
            "Duplicate transaction detected — linked case may affect resolution; "
            "analyst must review both"
        )

    # Investigation coverage
    coverage = plan.get("investigation_coverage") or {}
    tools_run = sum(1 for v in coverage.values() if v)
    total     = len(coverage)
    if total > 0 and tools_run == total:
        factors.append(f"Full investigation coverage ({tools_run}/{total} tools executed)")
    elif tools_run < total:
        factors.append(f"Partial investigation coverage ({tools_run}/{total} tools succeeded) — data gaps exist")

    if not factors:
        factors.append("Standard investigation criteria met")

    return factors


# ── Private helpers ───────────────────────────────────────────────────────────

def _historical_precedent_score(related: dict) -> float:
    """Score 0.0–1.0 based on historical case availability and resolution rate."""
    similar  = int(related.get("similar_cases") or 0)
    res_rate = float(related.get("resolution_rate") or 0.0)

    if similar == 0:
        return 0.15   # No precedent — low confidence

    # More cases and a higher resolution rate = stronger precedent
    if similar >= 10:
        base = 0.70
    elif similar >= 5:
        base = 0.55
    elif similar >= 2:
        base = 0.45
    else:
        base = 0.35

    # Resolution rate adjusts the base (0% rate = -0.10, 100% = +0.25)
    adjustment = (res_rate - 0.5) * 0.30
    return round(max(0.10, min(1.00, base + adjustment)), 2)


def _fraud_signal_alignment(plan: dict) -> float:
    """Score 0.0–1.0 based on whether fraud signals are consistent with category."""
    fraud_susp = plan.get("fraud_suspicion")
    category   = plan.get("dispute_category") or ""
    risk_tags  = plan.get("risk_tags") or []

    fraud_categories = {"Unauthorized Transaction", "Friendly Fraud"}
    non_fraud_categories = {"Duplicate Transaction", "Refund Not Received",
                            "Product Not Received", "Subscription Abuse", "ATM Cash Issue"}

    if category in fraud_categories and fraud_susp:
        return 0.90   # Consistent fraud case
    if category in non_fraud_categories and not fraud_susp:
        return 0.85   # Consistent non-fraud case
    if category in non_fraud_categories and fraud_susp:
        return 0.50   # Mixed signals — needs review
    if "POSSIBLE_FRAUD" in risk_tags or "SUSPICIOUS_BEHAVIOR" in risk_tags:
        return 0.60
    return 0.70       # Default moderate alignment


def _coverage_score(coverage: dict) -> float:
    """Score 0.0–1.0 based on how many investigation tools returned useful data."""
    if not coverage:
        return 0.50
    covered = sum(1 for v in coverage.values() if v)
    total   = len(coverage)
    return round(covered / total, 2) if total > 0 else 0.50
