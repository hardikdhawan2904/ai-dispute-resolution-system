"""
Keeps merchant_profiles, transactions, and dispute_history in sync with
live dispute_cases as cases are submitted and resolved.

Two entry points:
  sync_on_submission(case, db)  — called right after a new DisputeCase is persisted
  sync_on_resolution(case, db)  — called when status changes to Resolved/Rejected/Closed
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DisputeCase, MerchantProfile, Transaction, DisputeHistory
from utils.logger import api_logger

_TERMINAL_STATUSES = {"Resolved", "Rejected", "Closed"}
_FAVOR_MAP = {"Resolved": "customer", "Rejected": "merchant", "Closed": "partial"}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Food & Dining",    ["zomato", "swiggy", "restaurant", "cafe", "pizza", "burger", "food", "biryani", "dhaba", "bakery", "haldiram", "subway", "kfc", "domino"]),
    ("E-commerce",       ["amazon", "flipkart", "myntra", "meesho", "snapdeal", "nykaa", "jiomart", "ajio", "tata cliq", "indiamart"]),
    ("Travel",           ["irctc", "makemytrip", "ola", "uber", "rapido", "airlines", "goibibo", "yatra", "redbus", "indigo", "air india"]),
    ("Electronics",      ["croma", "reliance digital", "samsung", "apple store", "vijay sales", "boat", "electronics"]),
    ("Utilities",        ["jio recharge", "airtel", "bsnl", "tata power", "bescom", "msedcl", "indane", "bpcl", "electricity", "gas"]),
    ("Healthcare",       ["apollo", "netmeds", "1mg", "practo", "pharmeasy", "pharmacy", "hospital", "medical"]),
    ("Fuel",             ["indian oil", "hindustan petroleum", "shell", "reliance fuel", "petrol", "diesel", "fuel"]),
    ("Entertainment",    ["bookmyshow", "netflix", "hotstar", "amazon prime", "spotify", "youtube premium", "pvr", "inox"]),
    ("Education",        ["byju", "unacademy", "upgrad", "coursera", "vedantu", "education", "learning"]),
    ("Grocery",          ["bigbasket", "blinkit", "dmart", "grofer", "spencer", "zepto", "dunzo", "grocery"]),
    ("Banking Services", ["atm", "sbi atm", "hdfc bank atm", "icici bank atm", "axis bank atm", "kotak bank atm"]),
    ("Digital Wallet",   ["phonepe", "paytm", "gpay", "google pay", "mobikwik", "paysmart"]),
    ("NBFC",             ["quickloan", "cashtap", "rapidmoney", "nbfc", "finance", "loan"]),
    ("Insurance",        ["lic", "hdfc life", "max life", "bajaj allianz", "insurance"]),
    ("Apparel",          ["h&m", "zara", "fabindia", "raymond", "fashion", "clothing"]),
    ("Real Estate",      ["nobroker", "99acres", "magicbricks", "real estate"]),
]


def _infer_category(merchant_name: str) -> str:
    name = merchant_name.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in name for kw in keywords):
            return category
    return "Other"


def _parse_transaction_date(date_str: Optional[str], time_str: Optional[str]) -> datetime:
    """Parse form date/time strings into a UTC datetime. Falls back to now."""
    try:
        combined = f"{date_str} {time_str or '00:00'}".strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(combined, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    except Exception:
        pass
    return datetime.now(timezone.utc)


def _find_merchant(merchant_name: str, db: Session) -> Optional[MerchantProfile]:
    return (
        db.query(MerchantProfile)
        .filter(MerchantProfile.merchant_name.ilike(f"%{merchant_name[:40]}%"))
        .first()
    )


def _recompute_risk(profile: MerchantProfile) -> str:
    total = profile.total_disputes or 0
    txns  = profile.total_transactions or 1
    fraud = profile.fraud_complaints or 0
    rate  = total / txns
    if profile.blacklisted or rate > 0.15 or fraud >= 10:
        return "CRITICAL"
    if rate > 0.08 or fraud >= 5:
        return "HIGH"
    if rate > 0.03 or fraud >= 2:
        return "MEDIUM"
    return "LOW"


# ── Public API ────────────────────────────────────────────────────────────────

def sync_on_submission(case: DisputeCase, db: Session) -> None:
    """
    Called immediately after a DisputeCase row is flushed to the DB.
    - Upserts a Transaction record
    - Upserts a MerchantProfile and increments complaint counters
    """
    try:
        merchant_profile = _upsert_merchant_on_complaint(case, db)
        merchant_id = merchant_profile.merchant_id if merchant_profile else None
        _upsert_transaction(case, merchant_id, db)
    except Exception as exc:
        api_logger.warning(f"data_sync_service.sync_on_submission failed for {case.case_id}: {exc}")


def sync_on_resolution(case: DisputeCase, db: Session) -> None:
    """
    Called when a DisputeCase status changes to Resolved / Rejected / Closed.
    - Inserts (or updates) a DisputeHistory record
    - Updates MerchantProfile resolution counters
    """
    if case.status not in _TERMINAL_STATUSES:
        return
    try:
        _write_dispute_history(case, db)
        _update_merchant_resolution(case, db)
    except Exception as exc:
        api_logger.warning(f"data_sync_service.sync_on_resolution failed for {case.case_id}: {exc}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upsert_transaction(case: DisputeCase, merchant_id: Optional[str], db: Session) -> None:
    existing = db.query(Transaction).filter(
        Transaction.transaction_id == case.transaction_id
    ).first()

    if existing:
        # Transaction already in ledger — just flag it
        existing.is_disputed = True
    else:
        txn_dt = _parse_transaction_date(case.transaction_date, case.transaction_time)
        db.add(Transaction(
            transaction_id   = case.transaction_id,
            customer_id      = case.customer_id,
            merchant_id      = merchant_id,
            merchant_name    = case.merchant or "",
            amount           = case.amount,
            currency         = case.currency or "INR",
            transaction_type = case.transaction_type or "UPI",
            transaction_date = txn_dt,
            status           = "Success",   # disputed txns were successful debits
            location         = None,
            device_id        = None,
            is_disputed      = True,
            created_at       = txn_dt,
        ))


def _upsert_merchant_on_complaint(case: DisputeCase, db: Session) -> Optional[MerchantProfile]:
    if not case.merchant:
        return None

    profile = _find_merchant(case.merchant, db)

    if profile:
        profile.total_disputes  = (profile.total_disputes or 0) + 1
        if case.fraud_suspicion:
            profile.fraud_complaints = (profile.fraud_complaints or 0) + 1
        profile.risk_level = _recompute_risk(profile)
    else:
        category = _infer_category(case.merchant)
        fraud_ct = 1 if case.fraud_suspicion else 0
        # generate a unique merchant id that won't collide with seeded MERCH-XXXX ids
        count = db.query(MerchantProfile).count()
        mid   = f"MERCH-LIVE-{count + 1:05d}"
        profile = MerchantProfile(
            merchant_id             = mid,
            merchant_name           = case.merchant,
            merchant_category       = category,
            total_transactions      = 0,
            total_disputes          = 1,
            fraud_complaints        = fraud_ct,
            resolved_customer_favor = 0,
            resolved_merchant_favor = 0,
            risk_level              = "LOW",
            blacklisted             = False,
            created_at              = datetime.now(timezone.utc),
        )
        db.add(profile)
        db.flush()  # get the row into the session so callers can read merchant_id

    return profile


def _write_dispute_history(case: DisputeCase, db: Session) -> None:
    # Avoid duplicates — update if already exists
    existing = db.query(DisputeHistory).filter(
        DisputeHistory.case_id == case.case_id
    ).first()

    resolved_at = datetime.now(timezone.utc)
    favor       = _FAVOR_MAP.get(case.status, "partial")

    created = case.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    resolution_days = (resolved_at - created).days if created else 0

    resolution_text = _build_resolution_text(case)

    # Prefer merchant_id from the transaction record (exact match, avoids fuzzy-name errors)
    merchant_id = None
    if case.transaction_id:
        txn = db.query(Transaction).filter(
            Transaction.transaction_id == case.transaction_id
        ).first()
        if txn:
            merchant_id = txn.merchant_id
    if merchant_id is None and case.merchant:
        profile = _find_merchant(case.merchant, db)
        merchant_id = profile.merchant_id if profile else None

    if existing:
        existing.status               = case.status
        existing.resolved_in_favor_of = favor
        existing.resolution_days      = resolution_days
        existing.resolution           = resolution_text
        existing.resolved_at          = resolved_at
        existing.merchant_id          = merchant_id or existing.merchant_id
    else:
        db.add(DisputeHistory(
            case_id              = case.case_id,
            customer_id          = case.customer_id,
            merchant_id          = merchant_id,
            transaction_id       = case.transaction_id,
            dispute_category     = case.dispute_category or "Other",
            fraud_claim          = case.fraud_suspicion or False,
            amount               = case.amount,
            resolution           = resolution_text,
            resolved_in_favor_of = favor,
            resolution_days      = resolution_days,
            status               = case.status,
            created_at           = created or resolved_at,
            resolved_at          = resolved_at,
        ))


def _update_merchant_resolution(case: DisputeCase, db: Session) -> None:
    if not case.merchant:
        return
    profile = _find_merchant(case.merchant, db)
    if not profile:
        return

    favor = _FAVOR_MAP.get(case.status)
    if favor == "customer":
        profile.resolved_customer_favor = (profile.resolved_customer_favor or 0) + 1
    elif favor == "merchant":
        profile.resolved_merchant_favor = (profile.resolved_merchant_favor or 0) + 1


def _build_resolution_text(case: DisputeCase) -> str:
    if case.status == "Resolved":
        return (
            case.manual_review_reason
            or f"Dispute resolved in favour of customer. Category: {case.dispute_category}."
        )
    if case.status == "Rejected":
        return (
            case.manual_review_reason
            or f"Dispute rejected. Insufficient evidence to support {case.dispute_category} claim."
        )
    return case.manual_review_reason or "Case closed."

