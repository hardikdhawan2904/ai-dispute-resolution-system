"""
Agent 1 (ARIA) understanding tools — 4 deterministic BFSI analysers.

These tools process input data only — no DB queries, no external calls.
They give ARIA structured intelligence grounded in Indian banking / RBI standards
before it produces the final classification JSON.

Standards referenced:
  - RBI Circular on Limiting Customer Liability (July 2017)
  - NPCI UPI Dispute Resolution Framework
  - PCI-DSS v4.0 chargeback and fraud definitions
  - Indian Cyber Crime Coordination Centre (I4C) fraud patterns
"""
from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool

_INTL_SIGNALS = frozenset({
    ".com", "paypal", "apple", "google", "itunes", "netflix",
    "spotify", "steam", "alibaba", "amazon.com", "shopify",
    "stripe", "payoneer", "wise", "skrill", "coinbase",
})

# ── Tool 1 — Transaction risk analysis ────────────────────────────────────────

@tool
def assess_transaction_context(
    amount: float,
    transaction_type: str,
    merchant: str,
    transaction_date: str,
    transaction_time: str = "",
) -> str:
    """Assess full transaction context for risk signals per RBI/NPCI guidelines.
    Computes RBI liability tier, off-hours risk, card-not-present exposure,
    international merchant flags, and UPI/IMPS-specific India fraud patterns.
    Call this FIRST for every dispute — it anchors the risk baseline."""

    signals: list[str] = []
    risk_points = 0

    # ── RBI liability amount tiers (from RBI Circular 2017) ──────────────────
    if amount > 1_000_000:
        amount_tier  = "CRITICAL"
        risk_points += 5
        signals.append(f"Amount ₹{amount:,.0f} — exceeds ₹10L senior officer threshold")
    elif amount > 200_000:
        amount_tier  = "HIGH"
        risk_points += 4
        signals.append(f"Amount ₹{amount:,.0f} — above ₹2L bank escalation threshold")
    elif amount > 50_000:
        amount_tier  = "ELEVATED"
        risk_points += 3
        signals.append(f"Amount ₹{amount:,.0f} — above ₹50K heightened-scrutiny threshold")
    elif amount > 10_000:
        amount_tier  = "STANDARD"
        risk_points += 1
    else:
        amount_tier  = "LOW"

    # ── Hour-of-day analysis (I4C pattern: 80% of cyber fraud between 10pm–4am)
    hour = -1
    if transaction_time:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                hour = datetime.strptime(transaction_time.split(".")[0], fmt).hour
                break
            except ValueError:
                continue

    off_hours = (0 <= hour <= 4) or (hour == 23)
    late_evening = 20 <= hour <= 22
    if off_hours:
        risk_points += 3
        signals.append(f"Transaction at {hour:02d}:xx — I4C high-risk fraud window (10pm–4am)")
    elif late_evening:
        risk_points += 1
        signals.append(f"Transaction in late evening ({hour:02d}:xx) — elevated vigilance")

    # ── Weekday / weekend analysis ────────────────────────────────────────────
    is_weekend = False
    if transaction_date:
        try:
            wd = datetime.strptime(transaction_date, "%Y-%m-%d").weekday()
            is_weekend = wd >= 5
            if is_weekend:
                signals.append("Weekend transaction — bank support unavailable; delayed discovery risk")
        except ValueError:
            pass

    # ── Transaction type risk (NPCI / PCI-DSS) ───────────────────────────────
    cnp_types = {"UPI", "Net Banking", "Online Purchase", "International"}
    is_cnp = transaction_type in cnp_types
    if is_cnp:
        risk_points += 2
        signals.append(f"Card-not-present ({transaction_type}) — higher chargeback risk under PCI-DSS")

    # UPI-specific: second most common fraud channel in India (NPCI data)
    if transaction_type == "UPI":
        signals.append("UPI transaction — check for collect-request fraud, fake QR, and phishing VPA")

    # IMPS/NEFT: irreversible — RBI mandates extra verification
    if transaction_type == "Net Banking":
        signals.append("Net Banking (NEFT/RTGS/IMPS) — funds transfer largely irreversible post-settlement")

    # ── International merchant detection ─────────────────────────────────────
    merchant_lower = merchant.lower()
    is_intl = any(s in merchant_lower for s in _INTL_SIGNALS)
    if is_intl:
        risk_points += 2
        signals.append("International / digital-goods merchant — FEMA reporting may apply above USD 25,000")

    # ── Composite risk level (weighted) ──────────────────────────────────────
    if risk_points >= 8:
        risk_level = "CRITICAL"
    elif risk_points >= 5:
        risk_level = "HIGH"
    elif risk_points >= 2:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    signals_str = "\n".join(f"  • {s}" for s in signals) if signals else "  None detected"

    return (
        "TRANSACTION RISK ANALYSIS\n"
        f"  Amount               : ₹{amount:,.2f} (RBI Tier: {amount_tier})\n"
        f"  Type                 : {transaction_type} ({'CNP — elevated risk' if is_cnp else 'Standard'})\n"
        f"  Merchant             : {merchant} ({'International pattern' if is_intl else 'Domestic'})\n"
        f"  Date / Day           : {transaction_date} ({'Weekend' if is_weekend else 'Weekday'})\n"
        f"  Time                 : {f'{hour:02d}:xx' if hour >= 0 else 'Not provided'}"
        f" ({'HIGH-RISK OFF-HOURS' if off_hours else 'Normal'})\n"
        f"  Composite Risk       : {risk_level} (signal points: {risk_points})\n"
        f"  Active Risk Signals:\n{signals_str}"
    )


# ── Tool 2 — Fraud indicator scoring ──────────────────────────────────────────
# Scoring calibrated to I4C (Indian Cyber Crime Coordination Centre) fraud taxonomy
# and RBI's published cyber fraud data (Annual Report 2023-24).

_FRAUD_KEYWORDS = {
    # Customer denial phrases
    "didn't do", "did not do", "i did not", "not me", "not mine",
    "unauthorized", "not authorised", "not authorized", "without my",
    "someone else", "i never", "never did",
    # Fraud type keywords
    "hacked", "stolen", "stole", "fraud", "scam",
    "deceived", "cheated", "tricked",
    # India-specific attack vectors (I4C taxonomy)
    "phishing", "otp", "vishing", "sim swap",
    "account takeover", "no idea",
    "fake call", "impersonation", "screen share",
    "remote access", "anydesk", "teamviewer",
    "upi collect", "qr code scam", "fake upi",
    "kyc update", "account blocked", "arrested",  # common vishing pretexts
}


@tool
def score_fraud_indicators(
    customer_comment: str,
    customer_id: str = "",
    transaction_id: str = "",
    otp_received: str = "Not provided",
    otp_shared: str = "Not provided",
    bank_impersonation: str = "Not provided",
    remote_access: str = "Not provided",
    phishing_link: str = "Not provided",
    sim_swap_suspected: str = "Not provided",
    card_lost: str = "Not provided",
    device_lost: str = "Not provided",
    bank_contacted: str = "Not provided",
    card_blocked: str = "Not provided",
    collect_request: str = "Not provided",
) -> str:
    """Score fraud indicators using RBI/I4C taxonomy with DB-first evidence.
    Queries bank system records (account_events, customer_devices, transactions)
    first. Form answers are secondary confirmation — DB-verified signals carry
    full weight, form-only signals carry reduced weight (customer claims unverified).
    Calibrated to Indian cyber fraud patterns (NPCI Annual Fraud Report 2024)."""

    def is_yes(v: str) -> bool:
        return str(v).strip().lower() in {"yes", "true", "1"}

    score:      float     = 0.0
    indicators: list[str] = []
    comment_lower = customer_comment.lower()

    # ── Step 1: Query DB for bank-observed signals ────────────────────────────
    db_sim_swap       = False
    db_device_new     = False
    db_mobile_change  = False
    db_device_id      = ""
    db_card_lost      = False
    db_card_blocked   = False
    db_otp_delivered  = False
    db_bank_contacted = False
    db_collect_req    = False

    if customer_id:
        try:
            from database.database import SessionLocal
            from database.models import AccountEvent, CustomerDevice, Transaction
            from datetime import datetime, timezone, timedelta
            _db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                cutoff = now - timedelta(days=30)

                events = _db.query(AccountEvent).filter(
                    AccountEvent.customer_id == customer_id.upper(),
                    AccountEvent.event_timestamp >= cutoff,
                ).all()
                event_types = {e.event_type for e in events}

                # Bank-observed signals (primary source of truth)
                db_sim_swap       = "SIM_SWAP_DETECTED"           in event_types
                db_mobile_change  = "MOBILE_NUMBER_CHANGED"        in event_types
                db_device_new     = "DEVICE_REGISTERED"            in event_types
                db_card_lost      = "CARD_LOST_REPORTED"           in event_types
                db_card_blocked   = "CARD_BLOCKED"                 in event_types
                db_otp_delivered  = "OTP_DELIVERED"                in event_types
                db_bank_contacted = "CUSTOMER_CONTACT_LOGGED"      in event_types
                db_collect_req    = "UPI_COLLECT_REQUEST_RECEIVED" in event_types

                # Check if transaction device is unregistered
                if transaction_id:
                    txn = _db.query(Transaction).filter(
                        Transaction.transaction_id == transaction_id
                    ).first()
                    if txn and txn.device_id:
                        db_device_id = txn.device_id
                        dev = _db.query(CustomerDevice).filter(
                            CustomerDevice.customer_id == customer_id.upper(),
                            CustomerDevice.device_id == txn.device_id,
                            CustomerDevice.trusted == True,
                        ).first()
                        if not dev:
                            db_device_new = True
            finally:
                _db.close()
        except Exception:
            pass   # DB unavailable — fall through to form-only

    def _score_signal(
        db_confirmed: bool,
        form_value: str,
        full_score: float,
        label_verified: str,
        label_form: str,
    ) -> float:
        """Score a signal: full weight if DB confirms, 60% if form-only."""
        if db_confirmed and is_yes(form_value):
            indicators.append(f"{label_verified} [DB VERIFIED + CUSTOMER CONFIRMED]")
            return full_score
        elif db_confirmed:
            indicators.append(f"{label_verified} [DB VERIFIED]")
            return full_score
        elif is_yes(form_value):
            indicators.append(f"{label_form} [CUSTOMER REPORTED — unverified]")
            return round(full_score * 0.6, 1)   # 40% discount for unverified claim
        return 0.0

    # ── Step 2: Keyword scan (from customer narrative) ────────────────────────
    matched = [kw for kw in _FRAUD_KEYWORDS if kw in comment_lower]
    if matched:
        kw_score = min(len(matched) * 2.0, 6.0)
        score += kw_score
        indicators.append(f"Fraud language in description: {', '.join(matched[:6])}")

    # ── Step 3: I4C Tier-1 signals — DB-first ────────────────────────────────

    # SIM Swap — DB: SIM_SWAP_DETECTED event | Form: sim_swap_suspected
    score += _score_signal(
        db_sim_swap, sim_swap_suspected, 8.0,
        "SIM swap confirmed by bank telecom records — OTP bypass; RBI mandates zero liability",
        "SIM swap suspected by customer — OTP bypass possible; requires telecom verification",
    )

    # Bank Impersonation — no DB source (human call), form-only but with keyword boost
    if is_yes(bank_impersonation):
        boost = 2.0 if any(k in comment_lower for k in ("call", "phone", "fraud", "impersonation", "vishing")) else 0.0
        s = round(8.0 * 0.6 + boost, 1)
        score += s
        indicators.append(f"Bank impersonation call reported by customer [CUSTOMER REPORTED — keyword {'confirmed' if boost else 'not found'}]")

    # OTP Shared — no DB source (human action), form-only
    if is_yes(otp_shared):
        score += round(8.0 * 0.6, 1)
        indicators.append("OTP shared with third party [CUSTOMER REPORTED — social engineering vector]")

    # ── Step 4: I4C Tier-2 signals ────────────────────────────────────────────

    # New/unregistered device — DB: customer_devices + account_events
    score += _score_signal(
        db_device_new, "Not provided", 4.0,
        f"New or unregistered device '{db_device_id}' — not in trusted device registry",
        "New device reported by customer",
    )

    # Mobile number change — DB: account_events
    score += _score_signal(
        db_mobile_change, "Not provided", 4.0,
        "Mobile number changed in last 30 days — OTP interception risk",
        "Mobile change reported",
    )

    # Remote access — form-only (AnyDesk/TeamViewer)
    if is_yes(remote_access):
        score += round(4.0 * 0.6, 1)
        indicators.append("Remote access app installed [CUSTOMER REPORTED — device fully compromised if true]")

    # Phishing link — form-only
    if is_yes(phishing_link):
        score += round(4.0 * 0.6, 1)
        indicators.append("Phishing link clicked [CUSTOMER REPORTED — credential theft possible]")

    # ── Step 5: I4C Tier-3 (physical) — DB first ─────────────────────────────
    score += _score_signal(
        db_card_lost, card_lost, 2.5,
        "Card lost/stolen confirmed in bank records — physical theft vector; check PIN shoulder-surfing",
        "Card lost or stolen [CUSTOMER REPORTED — unverified]",
    )
    if is_yes(device_lost):
        score += round(2.5 * 0.6, 1)
        indicators.append("Device lost or stolen [CUSTOMER REPORTED — no bank record available]")

    # ── OTP received but denies initiating — DB preferred ────────────────────
    # Check DB first: OTP_DELIVERED event confirms bank did send an OTP
    otp_deny = any(k in comment_lower for k in ("didn't do", "not me", "unauthorized", "did not", "i never"))
    if db_otp_delivered and otp_deny:
        score += 3.5
        indicators.append("OTP delivery confirmed by bank records — customer denies initiating transaction [DB VERIFIED]")
    elif is_yes(otp_received) and otp_deny:
        score += round(3.5 * 0.7, 1)
        indicators.append("OTP received (customer reported) but transaction denied — classic social engineering [CUSTOMER REPORTED]")

    # ── UPI Collect Request — DB first ───────────────────────────────────────
    if db_collect_req:
        score += 4.0
        indicators.append("UPI collect request confirmed by bank payment records [DB VERIFIED] — victim approved outgoing transfer")
    elif is_yes(collect_request):
        score += round(4.0 * 0.6, 1)
        indicators.append("UPI collect request fraud reported by customer [CUSTOMER REPORTED — unverified]")

    # ── Protective actions — DB preferred ────────────────────────────────────
    protective: list[str] = []
    if db_bank_contacted:
        protective.append("bank contact logged in CRM records [DB VERIFIED]")
    elif is_yes(bank_contacted):
        protective.append("bank contacted (customer reported)")
    if db_card_blocked:
        protective.append("card block confirmed in bank card management system [DB VERIFIED]")
    elif is_yes(card_blocked):
        protective.append("card / account blocked (customer reported)")

    # ── Signal level ──────────────────────────────────────────────────────────
    level = (
        "CRITICAL" if score >= 14 else
        "HIGH"     if score >= 7  else
        "MEDIUM"   if score >= 3  else
        "LOW"      if score >= 1  else
        "NONE"
    )

    if level in ("CRITICAL", "HIGH"):
        liability = "BANK LIABILITY — fraud reported within RBI zero-liability window; credit within 10 working days"
    elif level == "MEDIUM":
        liability = "REQUIRES ASSESSMENT — analyst to determine contributory negligence"
    else:
        liability = "STANDARD — process per dispute category guidelines"

    indicators_str = "\n".join(f"  • {i}" for i in indicators) if indicators else "  None detected"

    return (
        "FRAUD INDICATOR ANALYSIS (I4C / RBI Taxonomy — DB-First)\n"
        f"  Fraud Signal Level   : {level} (score: {score:.1f})\n"
        f"  Evidence Mode        : {'DB-VERIFIED' if (db_sim_swap or db_device_new or db_mobile_change) else 'CUSTOMER-REPORTED'}\n"
        f"  Active Indicators:\n{indicators_str}\n"
        f"  Protective Steps     : {', '.join(protective) if protective else 'None taken'}\n"
        f"  RBI Liability        : {liability}"
    )


# ── Tool 3 — Evidence document verification ───────────────────────────────────

@tool
def verify_evidence_match(
    document_text: str,
    claimed_amount: str,
    claimed_merchant: str,
    dispute_description: str,
) -> str:
    """Verify whether submitted evidence supports the customer's claim.
    Checks amount match, merchant match, document type relevance,
    and flags contradictions that indicate friendly fraud.
    Returns MATCH, PARTIAL_MATCH, MISMATCH, NO_DOCUMENTS, or CANNOT_VERIFY."""

    doc_lower = document_text.lower().strip()

    if not doc_lower or doc_lower in {"no documents attached.", "no documents attached"}:
        return (
            "EVIDENCE VERIFICATION\n"
            "  Verdict              : NO_DOCUMENTS\n"
            "  Evidence Match       : null\n"
            "  Note                 : No documents submitted. Case will be routed to "
            "Pending Documents or assessed on statement data only."
        )

    if "ocr text reading is unavailable" in doc_lower or "automatic ocr" in doc_lower:
        return (
            "EVIDENCE VERIFICATION\n"
            "  Verdict              : CANNOT_VERIFY\n"
            "  Evidence Match       : null\n"
            "  Note                 : Document submitted but OCR extraction failed. "
            "Analyst must manually review the attachment."
        )

    # ── Amount matching ───────────────────────────────────────────────────────
    amount_clean = (
        str(claimed_amount)
        .replace(",", "").replace("INR", "").replace("₹", "")
        .replace("Rs", "").replace("rs", "").replace(" ", "").strip()
    )
    doc_no_commas = document_text.replace(",", "").replace(" ", "")
    amount_match = bool(amount_clean) and (
        amount_clean in doc_no_commas or
        # Also try integer match (some receipts drop decimals)
        amount_clean.split(".")[0] in doc_no_commas
    )

    # ── Merchant name matching ────────────────────────────────────────────────
    merchant_words = [w.lower() for w in claimed_merchant.split() if len(w) > 2]
    merchant_match = bool(merchant_words) and any(w in doc_lower for w in merchant_words)

    # ── Document type detection (financial relevance) ─────────────────────────
    strong_financial = [
        "bank statement", "account statement", "transaction receipt",
        "payment receipt", "tax invoice", "debit advice", "credit advice",
        "order confirmation", "delivery confirmation", "atm receipt",
        "upi transaction", "ref no", "reference number", "transaction id",
        "txn id", "utr number", "settlement",
    ]
    weak_financial = [
        "amount", "total", "payment", "charged", "debit", "credit",
        "balance", "date", "receipt", "invoice", "order",
    ]

    has_strong_doc = any(k in doc_lower for k in strong_financial)
    has_weak_doc   = any(k in doc_lower for k in weak_financial)
    doc_is_financial = has_strong_doc or (has_weak_doc and (amount_match or merchant_match))

    # ── Contradiction detection (friendly fraud signals) ──────────────────────
    # Only flag when the contradiction is unambiguous — false positives destroy trust.
    # Rule: a phrase must be semantically incompatible with the claim, not just lexically overlapping.
    # Refund receipts, cancellation confirmations, and merchant communications are SUPPORTING
    # evidence for most dispute types — never treat them as contradictions.
    contradictions: list[str] = []
    desc_lower = dispute_description.lower()

    # 1. Bank explicitly approved a transaction the customer says they didn't do
    if "approved" in doc_lower and ("unauthorized" in desc_lower or "not me" in desc_lower):
        contradictions.append(
            "Document shows bank-approved transaction while customer claims unauthorised"
        )

    # 2. Carrier/merchant delivery receipt vs "not received" claim
    # Must be an explicit delivery-completion phrase, not just the word "delivered"
    _delivery_complete = [
        "delivered successfully", "order delivered", "delivery confirmed",
        "shipment delivered", "package delivered", "delivery complete",
        "successfully delivered",
    ]
    if any(p in doc_lower for p in _delivery_complete) and "not received" in desc_lower:
        contradictions.append(
            "Delivery confirmation in document conflicts with 'not received' claim"
        )

    # 3. Bank/merchant confirms refund was CREDITED vs "refund not received"
    # "refund initiated" / "refund confirmation" / "refund receipt" are NOT credits —
    # they mean the process started but the money hasn't arrived yet, which SUPPORTS the claim.
    _refund_credited = [
        "refund successful", "refund completed", "refund credited to your account",
        "amount credited to", "credit processed successfully",
    ]
    if any(p in doc_lower for p in _refund_credited) and "refund not received" in desc_lower:
        contradictions.append(
            "Refund completion confirmation in document conflicts with 'refund not received' claim"
        )

    # ── Verdict logic ─────────────────────────────────────────────────────────
    match_signals = sum([amount_match, merchant_match, doc_is_financial])

    if contradictions:
        verdict     = "MISMATCH"
        match_bool  = "false"
        note = f"Document contradicts the claim: {'; '.join(contradictions)}. Possible friendly fraud."
    elif match_signals >= 2:
        verdict    = "MATCH"
        match_bool = "true"
        parts = (
            (["amount confirmed"] if amount_match else []) +
            (["merchant confirmed"] if merchant_match else []) +
            (["financial document type confirmed"] if doc_is_financial else [])
        )
        note = f"Document supports the claim ({', '.join(parts)})."
    elif match_signals == 1:
        verdict    = "PARTIAL_MATCH"
        match_bool = "true"
        note = "Document partially supports the claim — some transaction details found."
    else:
        verdict    = "MISMATCH"
        match_bool = "false"
        note = "Document does not corroborate the claimed transaction details."

    return (
        "EVIDENCE VERIFICATION\n"
        f"  Verdict              : {verdict}\n"
        f"  Evidence Match       : {match_bool}\n"
        f"  Amount Confirmed     : {'Yes' if amount_match else 'No'}\n"
        f"  Merchant Confirmed   : {'Yes' if merchant_match else 'No'}\n"
        f"  Financial Document   : {'Yes (strong)' if has_strong_doc else 'Yes (weak)' if has_weak_doc else 'No'}\n"
        f"  Contradictions       : {len(contradictions)} found\n"
        f"  Note                 : {note}"
    )


# ── Tool 4 — Confidence score calculator ─────────────────────────────────────
# Scoring model based on BFSI dispute classification benchmarks.
# Base score 0.50; adjustments reflect evidentiary weight.
# Final range: [0.10, 1.00] per industry standard confidence reporting.

@tool
def compute_confidence_score(
    fields_complete: bool,
    comment_quality: str,
    fraud_signal_level: str,
    fraud_category_consistent: bool,
    evidence_verdict: str,
    has_contradictions: bool,
) -> str:
    """Compute calibrated dispute classification confidence per BFSI standards.
    Call LAST — after assess_transaction_context, score_fraud_indicators,
    and verify_evidence_match — and use their outputs as inputs.

    fields_complete:           true if all core fields (amount, merchant, comment, date) present
    comment_quality:           'DETAILED' | 'MODERATE' | 'VAGUE'
    fraud_signal_level:        CRITICAL | HIGH | MEDIUM | LOW | NONE
    fraud_category_consistent: true if fraud signals align with dispute category
    evidence_verdict:          MATCH | PARTIAL_MATCH | MISMATCH | NO_DOCUMENTS | CANNOT_VERIFY
    has_contradictions:        true if customer statements or fields contradict each other"""

    score     = 0.30   # baseline — room for discrimination between strong and exceptional cases
    breakdown: list[str] = []

    # ── Data completeness (+/- 0.10) ─────────────────────────────────────────
    if fields_complete:
        score += 0.10
        breakdown.append("+0.10 all required transaction fields present")
    else:
        score -= 0.10
        breakdown.append("-0.10 incomplete transaction or customer details")

    # ── Comment quality (+/- 0.10) ───────────────────────────────────────────
    if comment_quality == "DETAILED":
        score += 0.10
        breakdown.append("+0.10 detailed customer account with specifics")
    elif comment_quality == "VAGUE":
        score -= 0.10
        breakdown.append("-0.10 vague description — insufficient detail for classification")

    # ── Fraud signal alignment (+/- 0.15) ────────────────────────────────────
    if fraud_category_consistent and fraud_signal_level in ("CRITICAL", "HIGH"):
        score += 0.15
        breakdown.append("+0.15 strong fraud indicators consistent with claimed category")
    elif fraud_category_consistent and fraud_signal_level == "MEDIUM":
        score += 0.08
        breakdown.append("+0.08 moderate fraud indicators consistent with claimed category")
    elif not fraud_category_consistent and fraud_signal_level in ("CRITICAL", "HIGH"):
        score -= 0.12
        breakdown.append("-0.12 high fraud signals but inconsistent with stated dispute type")

    # ── Evidence quality (highest impact: +0.25 / -0.25) ─────────────────────
    if evidence_verdict == "MATCH":
        score += 0.25
        breakdown.append("+0.25 submitted documents clearly corroborate the claim")
    elif evidence_verdict == "PARTIAL_MATCH":
        score += 0.10
        breakdown.append("+0.10 documents partially corroborate the claim")
    elif evidence_verdict == "MISMATCH":
        score -= 0.25
        breakdown.append("-0.25 documents contradict or do not support the claim")
    elif evidence_verdict == "CANNOT_VERIFY":
        score += 0.0
        breakdown.append("+0.00 document submitted but OCR unavailable — manual review required")
    # NO_DOCUMENTS: no adjustment (neutral — common for standard disputes)

    # ── Contradictions penalty ────────────────────────────────────────────────
    if has_contradictions:
        score -= 0.18
        breakdown.append("-0.18 internal contradictions between submission fields or statements")

    score = round(max(0.10, min(1.00, score)), 2)

    breakdown_str = "\n".join(f"  {b}" for b in breakdown)

    # ── Interpretation aligned with RBI review thresholds ────────────────────
    if score >= 0.80:
        interpretation = "High confidence — classification well-supported; automated processing appropriate"
    elif score >= 0.65:
        interpretation = "Good confidence — classification supported; standard analyst review sufficient"
    elif score >= 0.40:
        interpretation = "Moderate confidence — analyst verification recommended before decision"
    else:
        interpretation = "Low confidence — mandatory human review; do not auto-resolve"

    return (
        "CONFIDENCE SCORE CALCULATION\n"
        f"  Final Score          : {score:.2f} ({score * 100:.0f}%)\n"
        f"  Breakdown:\n{breakdown_str}\n"
        f"  Interpretation       : {interpretation}"
    )


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "assess_transaction_context": assess_transaction_context,
    "score_fraud_indicators":     score_fraud_indicators,
    "verify_evidence_match":      verify_evidence_match,
    # compute_confidence_score removed — confidence computed deterministically in finalize_node
}

