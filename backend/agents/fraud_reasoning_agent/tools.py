"""
Fraud Reasoning Agent tools — 3 tools that query database tables.
"""
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
import math
from typing import List

from langchain_core.tools import tool
from utils.logger import agent_logger

# Context variable to hold active case_id so we can exclude it from historical scans
_active_case_id: ContextVar[str] = ContextVar("active_case_id", default="")


# ── Tool 1 — Transaction Anomaly Detection ───────────────────────────────────

@tool
def detect_transaction_anomalies(customer_id: str, transaction_time: str, transaction_date: str) -> str:
    """Analyzes transaction time off-hours flags and short-term transaction velocity.
    Checks if transacted between 11 PM and 5 AM (off-hours) and counts other transactions in 24h.
    Use this to identify social engineering or mass withdrawal velocity spikes."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        # 1. Check Off-Hours (between 23:00 and 05:00)
        is_off_hours = False
        time_str = transaction_time.strip()
        if time_str:
            try:
                # Expecting HH:MM or HH:MM:SS
                parts = time_str.split(":")
                hour = int(parts[0])
                if hour >= 23 or hour < 5:
                    is_off_hours = True
            except Exception:
                pass

        # 2. Check 24-Hour Transaction Velocity
        exclude_id = _active_case_id.get()
        cutoff_dt = None
        if exclude_id:
            curr = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if curr and curr.created_at:
                cutoff_dt = curr.created_at
        
        now = cutoff_dt or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
            
        time_limit = now - timedelta(days=1)

        # Query other transactions for this customer in the last 24h
        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_date >= time_limit,
            Transaction.transaction_date <= now
        ).all()

        txn_count_24h = len(txns)

        # Velocity breach: any two transactions separated by < 15 seconds.
        # 3-per-day is normal card usage; rapid-fire pairs indicate scripted/automated fraud.
        _MIN_GAP_SECONDS = 15
        velocity_breach = False
        rapid_pair_gap_seconds: float | None = None
        sorted_txns = sorted(
            [t for t in txns if t.transaction_date is not None],
            key=lambda t: t.transaction_date,
        )
        for i in range(len(sorted_txns) - 1):
            a = sorted_txns[i].transaction_date
            b = sorted_txns[i + 1].transaction_date
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            gap = abs((b - a).total_seconds())
            if gap < _MIN_GAP_SECONDS:
                velocity_breach = True
                rapid_pair_gap_seconds = round(gap, 1)
                break

        status = "SUSPICIOUS" if (is_off_hours or velocity_breach) else "NORMAL"
        reasons = []
        if is_off_hours:
            reasons.append("Transaction processed during off-hours (11 PM - 5 AM).")
        if velocity_breach:
            reasons.append(
                f"Rapid-fire velocity breach: two transactions only {rapid_pair_gap_seconds}s apart "
                f"(threshold: {_MIN_GAP_SECONDS}s). Possible scripted or automated fraud."
            )

        assessment = " | ".join(reasons) if reasons else "Transaction patterns within normal velocity and timing limits."

        return (
            "TRANSACTION ANOMALY DETECTION REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Status               : {status}\n"
            f"  Transaction Date/Time: {transaction_date} {transaction_time}\n"
            f"  Off-Hours Flag       : {'Yes' if is_off_hours else 'No'}\n"
            f"  24h Transaction Count: {txn_count_24h}\n"
            f"  Velocity Breach      : {'Yes — ALERT' if velocity_breach else 'No'}"
            + (f"\n  Rapid-Fire Gap (sec) : {rapid_pair_gap_seconds}s" if velocity_breach else "") +
            f"\n  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_transaction_anomalies failed: {exc}")
        return f"TRANSACTION ANOMALY DETECTION REPORT\n  Error: Tool execution failed — {exc}\n  Status: SUSPICIOUS"
    finally:
        db.close()


# ── Location normalization helpers ────────────────────────────────────────────

# Indian state names and abbreviations — stripped when extracting the city token.
_STATE_TOKENS = {
    "maharashtra", "mh", "delhi", "dl", "ncr", "karnataka", "ka",
    "tamil nadu", "tn", "gujarat", "gj", "uttar pradesh", "up",
    "rajasthan", "rj", "west bengal", "wb", "andhra pradesh", "ap",
    "telangana", "ts", "kerala", "kl", "punjab", "pb", "haryana", "hr",
    "madhya pradesh", "mp", "odisha", "od", "or", "bihar", "br",
    "jharkhand", "jh", "assam", "as", "himachal pradesh", "hp",
    "uttarakhand", "uk", "goa", "ga", "chandigarh", "ch",
    "jammu", "kashmir", "jk", "chhattisgarh", "cg", "india",
}

_UNKNOWN_TOKENS = {"unknown", "n/a", "na", "none", "null", "", "-"}


def _extract_city(location: str) -> str:
    """
    Return the canonical city token from a free-text location string.

    Examples
    --------
    "Mumbai"              → "mumbai"
    "Mumbai, MH"          → "mumbai"
    "Andheri, Mumbai"     → "mumbai"
    "Andheri, Mumbai, MH" → "mumbai"
    "New Delhi, DL"       → "new delhi"
    """
    if not location:
        return ""
    parts = [p.strip().lower() for p in location.split(",")]
    parts = [p for p in parts if p and p not in _UNKNOWN_TOKENS]
    if not parts:
        return ""
    # Strip trailing state/country tokens until only the city remains
    while len(parts) > 1 and parts[-1] in _STATE_TOKENS:
        parts.pop()
    return parts[-1]


def _is_location_known(location: str) -> bool:
    """Return False when location is missing, blank, or a placeholder."""
    if not location or not location.strip():
        return False
    return location.strip().lower() not in _UNKNOWN_TOKENS


def _same_city(loc_a: str, loc_b: str) -> bool:
    """
    Return True when two location strings resolve to the same city.
    Uses substring containment to handle "Greater Mumbai" ↔ "Mumbai",
    "New Delhi" ↔ "Delhi", etc.
    """
    city_a = _extract_city(loc_a)
    city_b = _extract_city(loc_b)
    if not city_a or not city_b:
        return False
    return city_a == city_b or city_a in city_b or city_b in city_a


# ── Tool 2 — Location Velocity (Geovelocity) ──────────────────────────────────

@tool
def evaluate_location_velocity(customer_id: str, location: str, transaction_date: str, transaction_time: str) -> str:
    """Evaluates geographic velocity between consecutive transactions.
    Scans the ledger to see if the customer transacted from a different location in a time window
    that is physically impossible (e.g. different locations within < 4 hours).
    Use this to detect card cloning, location spoofing, or account takeover."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        if not _is_location_known(location):
            return (
                "GEOGRAPHIC VELOCITY REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Geovelocity Risk : LOW\n"
                "  Geovelocity Breach: No\n"
                "  Assessment       : Insufficient location data — geovelocity check skipped."
            )

        # Parse current transaction time
        try:
            curr_dt_str = f"{transaction_date} {transaction_time}"
            # Expecting YYYY-MM-DD HH:MM
            if len(transaction_time.split(":")) == 2:
                curr_dt = datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M")
            else:
                curr_dt = datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M:%S")
            curr_dt = curr_dt.replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)

        # Query transactions around that time
        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper()
        ).order_by(Transaction.transaction_date.desc()).all()

        if not txns:
            return (
                "GEOGRAPHIC VELOCITY REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Geovelocity Risk : LOW\n"
                "  Assessment       : No transaction logs found to evaluate location history."
            )

        # Find closest prior and subsequent transaction (excluding current transaction if ID matches)
        exclude_id = _active_case_id.get()
        curr_case = None
        if exclude_id:
            curr_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()

        curr_txn_id = curr_case.transaction_id if curr_case else None

        geovelocity_breach = False
        conflict_txn = None
        time_diff_hours = 0.0

        for t in txns:
            if curr_txn_id and t.transaction_id == curr_txn_id:
                continue
            
            t_dt = t.transaction_date.replace(tzinfo=timezone.utc) if t.transaction_date.tzinfo is None else t.transaction_date
            # Check if within 4 hours
            diff = abs((curr_dt - t_dt).total_seconds()) / 3600.0
            if diff < 4.0 and _is_location_known(t.location) and not _same_city(location, t.location):
                geovelocity_breach = True
                conflict_txn = t
                time_diff_hours = round(diff, 2)
                break

        if geovelocity_breach and conflict_txn:
            risk = "HIGH"
            assessment = (
                f"Impossible geovelocity breach! Transacted from '{location}' and "
                f"'{conflict_txn.location}' within {time_diff_hours} hours. "
                "This indicates impossible physical travel speed."
            )
        else:
            risk = "LOW"
            assessment = "Geographic transition frequency and location velocity are consistent."

        conflict_info = (
            f"  Conflict Location    : {conflict_txn.location}\n"
            f"  Conflict Txn Time    : {conflict_txn.transaction_date}\n"
            f"  Time Difference (Hrs): {time_diff_hours}\n"
        ) if geovelocity_breach and conflict_txn else ""

        return (
            "GEOGRAPHIC VELOCITY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Current Location     : {location}\n"
            f"  Geovelocity Breach   : {'Yes — ALERT' if geovelocity_breach else 'No'}\n"
            f"  Geovelocity Risk     : {risk}\n"
            + conflict_info +
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_location_velocity failed: {exc}")
        return f"GEOGRAPHIC VELOCITY REPORT\n  Error: Tool execution failed — {exc}\n  Geovelocity Risk: HIGH"
    finally:
        db.close()


# ── Tool 3 — Spending Behavior analysis ───────────────────────────────────────

@tool
def analyze_spending_behavior(customer_id: str, amount: float) -> str:
    """Analyzes customer transaction spending history to flag behavioral deviations.
    Computes historical average spending and flags if the current transaction amount is an outlier
    (e.g., exceeds 3 standard deviations or is > 3x average amount).
    Use this to check for high-value transactional anomalies."""
    from database.database import SessionLocal
    from database.models import Transaction

    db = SessionLocal()
    try:
        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper()
        ).all()

        if not txns:
            return (
                "SPENDING BEHAVIOR REPORT\n"
                f"  Customer ID          : {customer_id}\n"
                "  Spending Deviation   : NORMAL\n"
                "  Average Spend Amount : 0.00\n"
                "  Deviation Factor (Z) : 0.00\n"
                "  Assessment           : No transaction logs available."
            )

        amounts = [t.amount for t in txns if t.amount]
        if not amounts:
            amounts = [amount]  # fallback

        count = len(amounts)
        avg_amount = sum(amounts) / count

        # Calculate standard deviation
        variance = sum((x - avg_amount) ** 2 for x in amounts) / count
        std_dev = math.sqrt(variance)

        # Z-score calculation
        z_score = 0.0
        if std_dev > 0:
            z_score = abs(amount - avg_amount) / std_dev
        
        z_score = round(z_score, 2)
        avg_amount = round(avg_amount, 2)

        amount_anomaly = False
        if z_score >= 3.0 or amount > (3 * avg_amount):
            amount_anomaly = True

        status = "ANOMALOUS" if amount_anomaly else "NORMAL"
        
        reasons = []
        if z_score >= 3.0:
            reasons.append(f"Amount flags severe statistical deviation (Z-score: {z_score} >= 3.0).")
        elif amount > (3 * avg_amount):
            reasons.append(f"Amount ₹{amount:,.2f} exceeds 3x customer average spending profile (₹{avg_amount:,.2f}).")
        
        assessment = " | ".join(reasons) if reasons else "Dispute amount is consistent with customer's typical transaction behavior."

        return (
            "SPENDING BEHAVIOR REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Dispute Amount       : ₹{amount:,.2f}\n"
            f"  Spending Deviation   : {status}\n"
            f"  Average Spend Amount : ₹{avg_amount:,.2f}\n"
            f"  Standard Deviation   : {std_dev:.2f}\n"
            f"  Deviation Factor (Z) : {z_score}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_spending_behavior failed: {exc}")
        return f"SPENDING BEHAVIOR REPORT\n  Error: Tool execution failed — {exc}\n  Spending Deviation: ANOMALOUS"
    finally:
        db.close()


# ── Tool 4 — KYC Profile verification ─────────────────────────────────────────

# Dispute types where a full KYC match is a red flag, not a green one —
# the fraudster has the victim's device/email and can supply all three fields.
_COMPROMISE_RISK_CATEGORIES = {"unauthorized transaction"}


@tool
def verify_kyc_match(customer_id: str, name: str, email: str, phone: str, dispute_category: str = "") -> str:
    """Compare dispute submission name, email, and phone against the bank's
    internal KYC/CIF database. Returns joining date and match flags.
    Use this to detect potential Identity Theft or account creation discrepancies."""
    from database.database import SessionLocal
    from database.models import BankCustomer

    db = SessionLocal()
    try:
        customer = db.query(BankCustomer).filter(
            BankCustomer.customer_id == customer_id.upper()
        ).first()

        if not customer:
            return (
                "KYC VERIFICATION REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Status           : FAILED\n"
                "  Reason           : Customer ID not found in bank's KYC records."
            )

        db_name = customer.full_name
        db_email = customer.email
        db_phone = customer.phone

        # Standardise and check matches
        name_clean = name.strip().lower()
        db_name_clean = db_name.strip().lower()

        name_match = (name_clean == db_name_clean) or (name_clean in db_name_clean) or (db_name_clean in name_clean)
        email_match = email.strip().lower() == db_email.strip().lower()

        # Phone check: ignore country code prefix (+91 or 91)
        p1 = "".join(filter(str.isdigit, phone))
        p2 = "".join(filter(str.isdigit, db_phone))
        phone_match = p1[-10:] == p2[-10:] if p1 and p2 else False

        all_match = name_match and email_match and phone_match
        any_match = name_match or email_match or phone_match

        # A full KYC match in a device/account-compromise category is ambiguous —
        # the fraudulent actor has physical access to the victim's phone and email,
        # so they can trivially supply the correct name, email, and phone.
        category_lower = dispute_category.strip().lower()
        compromise_risk = (
            "HIGH"
            if all_match and category_lower in _COMPROMISE_RISK_CATEGORIES
            else "NONE"
        )

        if compromise_risk == "HIGH":
            status = "SUSPICIOUS"
            note = (
                "All KYC fields match, but this is an Unauthorized Transaction dispute. "
                "A fraudulent actor with physical access to the victim's device and email "
                "can supply all three fields — a full match does not confirm the submitter "
                "is the legitimate account holder."
            )
        elif all_match:
            status = "VERIFIED"
            note = "All details correspond to KYC records."
        elif any_match:
            status = "SUSPICIOUS"
            mismatch_fields = []
            if not name_match: mismatch_fields.append("Name")
            if not email_match: mismatch_fields.append("Email")
            if not phone_match: mismatch_fields.append("Phone")
            note = f"Verification partial match. Mismatches in: {', '.join(mismatch_fields)}."
        else:
            status = "FAILED"
            note = "Name, email, and phone do not correspond to the customer ID record."

        return (
            "KYC VERIFICATION REPORT\n"
            f"  Customer ID      : {customer_id}\n"
            f"  Verification     : {status}\n"
            f"  Compromise Risk  : {compromise_risk}\n"
            f"  Name Match       : {'Yes' if name_match else 'No'} (Submitted: '{name}', KYC: '{db_name}')\n"
            f"  Email Match      : {'Yes' if email_match else 'No'} (Submitted: '{email}', KYC: '{db_email}')\n"
            f"  Phone Match      : {'Yes' if phone_match else 'No'} (Submitted: '{phone}', KYC: '{db_phone}')\n"
            f"  Joining Date     : {customer.joining_date or 'N/A'}\n"
            f"  Details          : {note}"
        )
    except Exception as exc:
        agent_logger.warning(f"verify_kyc_match failed: {exc}")
        return f"KYC VERIFICATION REPORT\n  Error: Tool execution failed — {exc}\n  Verification: FAILED"
    finally:
        db.close()


# ── Tool 5 — Device & Location analysis ───────────────────────────────────────

@tool
def evaluate_device_fingerprint(customer_id: str, device_id: str, location: str) -> str:
    """Analyze customer device IDs and transaction locations in historical logs
    to determine if this transaction was submitted from a recognized device/location.
    Use this to detect Account Takeover (ATO) or login frauds."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        if not device_id:
            return (
                "DEVICE & LOCATION FINGERPRINT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Device ID        : Not provided\n"
                "  Location         : Not provided\n"
                "  Device Risk      : MEDIUM\n"
                "  Assessment       : Missing device fingerprint metadata."
            )

        # Look up customer transactions
        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper()
        ).all()

        exclude_id = _active_case_id.get()
        curr_case = None
        if exclude_id:
            curr_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
        curr_txn_id = curr_case.transaction_id if curr_case else None

        if curr_txn_id:
            txns = [t for t in txns if t.transaction_id != curr_txn_id]

        total_txns = len(txns)
        if total_txns == 0:
            return (
                "DEVICE & LOCATION FINGERPRINT\n"
                f"  Customer ID      : {customer_id}\n"
                f"  Device ID        : {device_id}\n"
                f"  Location         : {location}\n"
                "  Device Risk      : MEDIUM\n"
                "  Assessment       : No transaction history to build fingerprint profile."
            )

        # Scrutinise device IDs and locations
        device_counts = Counter(t.device_id for t in txns if t.device_id)
        location_counts = Counter(t.location for t in txns if t.location)

        recognized_device = device_id in device_counts
        device_txn_count = device_counts.get(device_id, 0)
        device_frequency = device_txn_count / total_txns if total_txns > 0 else 0.0

        location_clean = location.strip().lower()
        location_consistent = False
        for loc, count in location_counts.items():
            if loc.strip().lower() in location_clean or location_clean in loc.strip().lower():
                location_consistent = True
                break

        if recognized_device and location_consistent:
            risk = "LOW"
            note = f"Device recognized ({device_txn_count} historical transactions) and location is consistent."
        elif recognized_device:
            risk = "MEDIUM"
            note = f"Device recognized ({device_txn_count} transactions) but transacted from atypical location '{location}'."
        elif location_consistent:
            risk = "MEDIUM"
            note = f"New device ID '{device_id}', but location is within customer's typical transaction area."
        else:
            risk = "HIGH"
            note = f"Unrecognized device ID '{device_id}' and atypical location '{location}' — strong Account Takeover signal."

        return (
            "DEVICE & LOCATION FINGERPRINT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Device ID            : {device_id}\n"
            f"  Recognised Device    : {'Yes' if recognized_device else 'No'} ({device_frequency:.1%} frequency)\n"
            f"  Location             : {location}\n"
            f"  Location Consistent  : {'Yes' if location_consistent else 'No'}\n"
            f"  Device Risk          : {risk}\n"
            f"  Assessment           : {note}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_device_fingerprint failed: {exc}")
        return f"DEVICE & LOCATION FINGERPRINT\n  Error: Tool execution failed — {exc}\n  Device Risk: HIGH"
    finally:
        db.close()


# ── Tool 6 — Dispute behavioral patterns ──────────────────────────────────────

@tool
def analyze_behavioral_patterns(customer_id: str) -> str:
    """Check prior dispute counts and resolution rates to spot high-frequency
    disputers, repeat friendly-fraud claims, or velocity anomalies.
    Use this to calculate behavioral trust indicators."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory

    db = SessionLocal()
    try:
        exclude_id = _active_case_id.get()
        cutoff_dt  = None
        if exclude_id:
            curr = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if curr and curr.created_at:
                cutoff_dt = curr.created_at

        # ── query history ────────────────────────────────────────────────────
        hist_q = db.query(DisputeHistory).filter(DisputeHistory.customer_id == customer_id)
        if cutoff_dt:
            hist_q = hist_q.filter(DisputeHistory.created_at < cutoff_dt)
        hist_cases = hist_q.all()

        # ── query live cases ─────────────────────────────────────────────────
        live_q = db.query(DisputeCase).filter(DisputeCase.customer_id == customer_id)
        if exclude_id:
            live_q = live_q.filter(DisputeCase.case_id != exclude_id)
        if cutoff_dt:
            live_q = live_q.filter(DisputeCase.created_at < cutoff_dt)
        live_cases = live_q.all()

        total = len(hist_cases) + len(live_cases)

        if total == 0:
            return (
                "DISPUTE BEHAVIOR REPORT\n"
                f"  Customer ID          : {customer_id}\n"
                "  Prior Disputes       : 0\n"
                "  Velocity Breach      : No\n"
                "  Resolution Profile   : No prior disputes\n"
                "  Friendly Fraud Risk  : LOW\n"
                "  Assessment           : Clean account with no history of disputes."
            )

        # Check velocity: disputes filed in last 30 days
        all_dates = []
        for c in hist_cases:
            if c.created_at:
                all_dates.append(c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at)
        for c in live_cases:
            if c.created_at:
                all_dates.append(c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at)

        now = datetime.now(timezone.utc)
        last_30d_count = sum(1 for d in all_dates if (now - d).days <= 30)
        velocity_breach = last_30d_count >= 2

        # Check resolutions
        resolved_total = sum(1 for c in hist_cases if c.status == "Resolved")
        resolved_merchant = sum(1 for c in hist_cases if c.status == "Resolved" and c.resolved_in_favor_of == "merchant")
        
        # High merchant favor resolution rate suggests friendly-fraud or low-integrity claims
        merchant_favour_rate = resolved_merchant / resolved_total if resolved_total > 0 else 0.0

        if velocity_breach or (total >= 4 and merchant_favour_rate > 0.6):
            risk = "HIGH"
            note = f"Multiple prior disputes ({total}) with high velocity ({last_30d_count} in last 30d) or merchant-favour rates ({merchant_favour_rate:.0%})."
        elif total >= 3 or merchant_favour_rate > 0.3:
            risk = "MEDIUM"
            note = f"Moderate dispute history ({total} cases). Merchant favor rate: {merchant_favour_rate:.0%}."
        else:
            risk = "LOW"
            note = f"Few previous disputes ({total} total). No velocity anomalies."

        return (
            "DISPUTE BEHAVIOR REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Prior Disputes       : {total}\n"
            f"  Disputes in Last 30d : {last_30d_count}\n"
            f"  Velocity Breach      : {'Yes — ALERT' if velocity_breach else 'No'}\n"
            f"  Resolved for Merchant: {resolved_merchant} of {resolved_total} resolved ({merchant_favour_rate:.0%})\n"
            f"  Friendly Fraud Risk  : {risk}\n"
            f"  Assessment           : {note}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_behavioral_patterns failed: {exc}")
        return f"DISPUTE BEHAVIOR REPORT\n  Error: Tool execution failed — {exc}\n  Friendly Fraud Risk: HIGH"
    finally:
        db.close()


# ── Tool 7 — Merchant Risk Intelligence (all channels) ────────────────────────

@tool
def evaluate_merchant_risk_intelligence(merchant_id: str, merchant_name: str) -> str:
    """Assess merchant risk from the bank's merchant profile database.
    Checks blacklist status, risk tier, fraud complaint volume, and resolution rates.
    Run for ALL transaction types."""
    from database.database import SessionLocal
    from database.models import MerchantProfile

    db = SessionLocal()
    try:
        merchant = None
        if merchant_id and merchant_id.strip():
            merchant = db.query(MerchantProfile).filter(
                MerchantProfile.merchant_id == merchant_id.upper()
            ).first()

        if not merchant and merchant_name and merchant_name.strip():
            merchant = db.query(MerchantProfile).filter(
                MerchantProfile.merchant_name.ilike(f"%{merchant_name.strip()}%")
            ).first()

        if not merchant:
            return (
                "MERCHANT RISK INTELLIGENCE REPORT\n"
                f"  Merchant             : {merchant_name or merchant_id or 'Unknown'}\n"
                "  Profile Found        : No\n"
                "  Merchant Risk Level  : LOW\n"
                "  Merchant Risk Score  : 0.00\n"
                "  Assessment           : Merchant not found in bank profiles — no risk data available."
            )

        blacklisted = bool(merchant.blacklisted)
        score = 0.0
        reasoning = []

        if blacklisted:
            score = 1.0
            reasoning.append("Merchant is BLACKLISTED — zero tolerance, highest risk")
        else:
            if merchant.risk_level == "CRITICAL":
                score += 0.30
                reasoning.append("Merchant risk tier: CRITICAL (+0.30)")
            elif merchant.risk_level == "HIGH":
                score += 0.15
                reasoning.append("Merchant risk tier: HIGH (+0.15)")
            elif merchant.risk_level == "MEDIUM":
                score += 0.10
                reasoning.append("Merchant risk tier: MEDIUM (+0.10)")

            if (merchant.fraud_complaints or 0) > 5:
                score += 0.10
                reasoning.append(f"High fraud complaint volume: {merchant.fraud_complaints} complaints (+0.10)")

            total_resolved = (merchant.resolved_customer_favor or 0) + (merchant.resolved_merchant_favor or 0)
            if (merchant.resolved_customer_favor or 0) > 0 and total_resolved > 0:
                cust_rate = merchant.resolved_customer_favor / total_resolved
                if cust_rate > 0.70:
                    score += 0.10
                    reasoning.append(f"High customer-favor resolution rate: {cust_rate:.0%} (+0.10)")

        score = round(min(1.0, max(0.0, score)), 2)

        if score >= 0.50:
            risk_level = "CRITICAL"
        elif score >= 0.30:
            risk_level = "HIGH"
        elif score >= 0.10:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        total_res = (merchant.resolved_customer_favor or 0) + (merchant.resolved_merchant_favor or 0)
        cust_pct = f"{merchant.resolved_customer_favor / total_res:.0%}" if total_res > 0 else "N/A"

        return (
            "MERCHANT RISK INTELLIGENCE REPORT\n"
            f"  Merchant             : {merchant.merchant_name}\n"
            f"  Merchant ID          : {merchant.merchant_id}\n"
            f"  Profile Found        : Yes\n"
            f"  Blacklisted          : {'Yes — CRITICAL ALERT' if blacklisted else 'No'}\n"
            f"  Risk Tier            : {merchant.risk_level}\n"
            f"  Fraud Complaints     : {merchant.fraud_complaints or 0}\n"
            f"  Customer-Favor Rate  : {cust_pct}\n"
            f"  Merchant Risk Score  : {score}\n"
            f"  Merchant Risk Level  : {risk_level}\n"
            f"  Reasoning            : {' | '.join(reasoning) if reasoning else 'No elevated risk signals'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_merchant_risk_intelligence failed: {exc}")
        return f"MERCHANT RISK INTELLIGENCE REPORT\n  Error: {exc}\n  Merchant Risk Level: LOW"
    finally:
        db.close()


# ── Tool 8 — Card Velocity (Card POS only) ────────────────────────────────────

@tool
def analyze_card_velocity(customer_id: str, transaction_date: str, transaction_time: str) -> str:
    """Check for card velocity abuse — multiple card transactions within a 5-minute window.
    Use only for Debit Card / Credit Card POS transactions."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        exclude_id = _active_case_id.get()
        cutoff_dt = None
        if exclude_id:
            curr = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if curr and curr.created_at:
                cutoff_dt = curr.created_at

        now = cutoff_dt or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        time_limit = now - timedelta(days=1)

        _CARD_TYPES = {"debit card", "credit card", "card", "debit", "credit"}
        txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.transaction_date >= time_limit,
                Transaction.transaction_date <= now,
            ).all()
            if (t.transaction_type or "").lower() in _CARD_TYPES
        ]

        count_24h = len(txns)
        velocity_breach = False
        window_count = 0

        sorted_txns = sorted([t for t in txns if t.transaction_date], key=lambda t: t.transaction_date)
        for i, base in enumerate(sorted_txns):
            base_dt = base.transaction_date
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
            in_window = 1
            for j in range(i + 1, len(sorted_txns)):
                other_dt = sorted_txns[j].transaction_date
                if other_dt.tzinfo is None:
                    other_dt = other_dt.replace(tzinfo=timezone.utc)
                if abs((other_dt - base_dt).total_seconds()) <= 300:
                    in_window += 1
                else:
                    break
            if in_window >= 3:
                velocity_breach = True
                window_count = in_window
                break

        risk_level = "HIGH" if velocity_breach else "LOW"
        assessment = (
            f"Card velocity breach: {window_count} card transactions within 5-minute window — possible cloned card or scripted fraud."
            if velocity_breach else
            "Card usage frequency within normal limits."
        )

        return (
            "CARD VELOCITY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  24h Card Txn Count   : {count_24h}\n"
            f"  Velocity Breach      : {'Yes — ALERT' if velocity_breach else 'No'}\n"
            f"  Risk Level           : {risk_level}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_card_velocity failed: {exc}")
        return f"CARD VELOCITY REPORT\n  Error: {exc}\n  Risk Level: LOW"
    finally:
        db.close()


# ── Tool 9 — ATM-POS Distance (Card POS only) ────────────────────────────────

@tool
def evaluate_atm_pos_distance(customer_id: str, transaction_date: str, transaction_time: str, location: str) -> str:
    """Check for impossible travel between ATM withdrawals and POS transactions.
    Compares current POS location against recent ATM transactions within 1 hour.
    Use only for Card POS transactions."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        if not _is_location_known(location):
            return (
                "ATM-POS DISTANCE REPORT\n"
                f"  Customer ID          : {customer_id}\n"
                "  Impossible Travel    : No\n"
                "  Assessment           : Insufficient location data — check skipped."
            )

        try:
            curr_dt_str = f"{transaction_date} {transaction_time}"
            curr_dt = datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M") if len(transaction_time.split(":")) == 2 \
                else datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M:%S")
            curr_dt = curr_dt.replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)

        window_start = curr_dt - timedelta(hours=2)

        _ATM_TYPES = {"atm", "atm cash", "atm withdrawal", "cash withdrawal"}
        atm_txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.transaction_date >= window_start,
                Transaction.transaction_date <= curr_dt,
            ).all()
            if (t.transaction_type or "").lower() in _ATM_TYPES
        ]

        impossible_travel = False
        conflict_location = None
        conflict_diff_mins = 0.0

        for t in atm_txns:
            if not _is_location_known(t.location):
                continue
            if not _same_city(location, t.location):
                t_dt = t.transaction_date
                if t_dt.tzinfo is None:
                    t_dt = t_dt.replace(tzinfo=timezone.utc)
                diff_mins = abs((curr_dt - t_dt).total_seconds()) / 60
                if diff_mins <= 60:
                    impossible_travel = True
                    conflict_location = t.location
                    conflict_diff_mins = round(diff_mins, 1)
                    break

        return (
            "ATM-POS DISTANCE REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Current POS Location : {location}\n"
            f"  Impossible Travel    : {'Yes — ALERT' if impossible_travel else 'No'}\n"
            + (f"  Conflicting ATM Loc  : {conflict_location}\n"
               f"  Time Difference      : {conflict_diff_mins} minutes\n" if impossible_travel else "") +
            f"  Distance Risk        : {'HIGH' if impossible_travel else 'LOW'}\n"
            f"  Assessment           : {'Impossible physical movement between ATM and POS locations within ' + str(conflict_diff_mins) + ' minutes.' if impossible_travel else 'No impossible travel detected between ATM and POS locations.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_atm_pos_distance failed: {exc}")
        return f"ATM-POS DISTANCE REPORT\n  Error: {exc}\n  Distance Risk: LOW"
    finally:
        db.close()


# ── Tool 10 — Foreign Usage (Card POS only) ───────────────────────────────────

@tool
def analyze_foreign_usage(customer_id: str, merchant: str, location: str) -> str:
    """Detect if a card is being used internationally when the customer normally transacts domestically.
    Use for Card POS transactions."""
    from database.database import SessionLocal
    from database.models import Transaction

    db = SessionLocal()
    try:
        _INDIA_TOKENS = {
            "india", "mumbai", "delhi", "bangalore", "chennai", "hyderabad",
            "kolkata", "pune", "ahmedabad", "jaipur", "lucknow", "surat",
            "kanpur", "nagpur", "indore", "bhopal", "patna", "vadodara",
            "mh", "dl", "ka", "tn", "ts", "ap", "gj", "up", "rj", "wb",
        }
        _INTL_INDICATORS = {
            "usa", "us", "united states", "uk", "united kingdom", "uae", "dubai",
            "singapore", "malaysia", "thailand", "china", "japan", "germany",
            "france", "australia", "canada", "nepal", "sri lanka", "bangladesh",
        }

        def _is_india(loc: str) -> bool:
            if not loc:
                return True  # assume domestic if unknown
            loc_l = loc.lower()
            return any(t in loc_l for t in _INDIA_TOKENS)

        def _is_international(loc: str, merch: str) -> bool:
            combined = (loc + " " + merch).lower()
            return any(t in combined for t in _INTL_INDICATORS)

        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper()
        ).order_by(Transaction.transaction_date.desc()).limit(50).all()

        if not txns:
            return (
                "FOREIGN USAGE REPORT\n"
                f"  Customer ID          : {customer_id}\n"
                "  Foreign Usage        : No\n"
                "  Assessment           : No transaction history to compare."
            )

        domestic_count = sum(1 for t in txns if _is_india(t.location or ""))
        domestic_pct = domestic_count / len(txns)

        current_is_intl = _is_international(location, merchant)
        foreign_usage = domestic_pct >= 0.90 and current_is_intl

        return (
            "FOREIGN USAGE REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Historical Domestic  : {domestic_pct:.0%} of last {len(txns)} transactions\n"
            f"  Current Location     : {location or 'Not provided'}\n"
            f"  Current Merchant     : {merchant}\n"
            f"  Foreign Usage        : {'Yes — ALERT' if foreign_usage else 'No'}\n"
            f"  Assessment           : {'Customer predominantly transacts domestically but current transaction shows international pattern.' if foreign_usage else 'No unusual geographic shift detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_foreign_usage failed: {exc}")
        return f"FOREIGN USAGE REPORT\n  Error: {exc}\n  Foreign Usage: No"
    finally:
        db.close()


# ── Tool 11 — Card Present Anomalies (Card POS only) ─────────────────────────

@tool
def analyze_card_present_anomalies(customer_id: str, merchant: str, amount: float, transaction_time: str) -> str:
    """Detect anomalies in card-present (POS) transactions: unusual merchant category,
    unusual purchase time, or unusual spend amount compared to POS history.
    Use for Debit Card / Credit Card POS transactions."""
    from database.database import SessionLocal
    from database.models import Transaction

    db = SessionLocal()
    try:
        _CARD_TYPES = {"debit card", "credit card", "card", "debit", "credit"}
        _HIGH_RISK_MERCHANTS = {"jewellery", "jewelry", "electronics", "forex", "casino", "gaming", "gold", "diamond", "luxury"}

        txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper()
            ).order_by(Transaction.transaction_date.desc()).limit(30).all()
            if (t.transaction_type or "").lower() in _CARD_TYPES
        ]

        avg_amount = sum(t.amount for t in txns) / len(txns) if txns else amount
        amount_anomaly = amount > (avg_amount * 3) if avg_amount > 0 else False

        time_anomaly = False
        try:
            hour = int(transaction_time.split(":")[0])
            time_anomaly = hour >= 22 or hour < 6
        except Exception:
            pass

        merchant_lower = merchant.lower()
        merchant_anomaly = any(kw in merchant_lower for kw in _HIGH_RISK_MERCHANTS)

        anomaly_count = sum([amount_anomaly, time_anomaly, merchant_anomaly])
        anomaly_score = round(min(1.0, anomaly_count * 0.15), 2)

        flags = []
        if amount_anomaly:
            flags.append(f"Amount {amount:,.2f} is {amount/avg_amount:.1f}x above POS average ({avg_amount:,.2f})")
        if time_anomaly:
            flags.append(f"Transaction at off-hours (time: {transaction_time})")
        if merchant_anomaly:
            flags.append(f"High-risk merchant category detected: {merchant}")

        return (
            "CARD PRESENT ANOMALY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Merchant             : {merchant}\n"
            f"  Amount               : {amount:,.2f}\n"
            f"  Avg POS Amount       : {avg_amount:,.2f}\n"
            f"  Amount Anomaly       : {'Yes' if amount_anomaly else 'No'}\n"
            f"  Time Anomaly         : {'Yes' if time_anomaly else 'No'}\n"
            f"  Merchant Anomaly     : {'Yes' if merchant_anomaly else 'No'}\n"
            f"  Anomaly Score        : {anomaly_score}\n"
            f"  Flags                : {' | '.join(flags) if flags else 'None'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_card_present_anomalies failed: {exc}")
        return f"CARD PRESENT ANOMALY REPORT\n  Error: {exc}\n  Anomaly Score: 0.0"
    finally:
        db.close()


# ── Tool 12 — ATM Velocity (ATM only) ────────────────────────────────────────

@tool
def analyze_atm_velocity(customer_id: str, transaction_date: str, transaction_time: str) -> str:
    """Check for multiple ATM cash withdrawals within a short time window (1 hour).
    Use only for ATM transactions."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        exclude_id = _active_case_id.get()
        cutoff_dt = None
        if exclude_id:
            curr = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if curr and curr.created_at:
                cutoff_dt = curr.created_at

        now = cutoff_dt or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        time_limit = now - timedelta(days=1)

        _ATM_TYPES = {"atm", "atm cash", "atm withdrawal", "cash withdrawal"}
        txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.transaction_date >= time_limit,
                Transaction.transaction_date <= now,
            ).all()
            if (t.transaction_type or "").lower() in _ATM_TYPES and t.transaction_date
        ]

        count_24h = len(txns)
        velocity_breach = False
        window_count = 0

        sorted_txns = sorted(txns, key=lambda t: t.transaction_date)
        for i, base in enumerate(sorted_txns):
            base_dt = base.transaction_date
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
            in_window = 1
            for j in range(i + 1, len(sorted_txns)):
                other_dt = sorted_txns[j].transaction_date
                if other_dt.tzinfo is None:
                    other_dt = other_dt.replace(tzinfo=timezone.utc)
                if abs((other_dt - base_dt).total_seconds()) <= 3600:
                    in_window += 1
                else:
                    break
            if in_window >= 3:
                velocity_breach = True
                window_count = in_window
                break

        risk_level = "HIGH" if velocity_breach else "LOW"
        assessment = (
            f"ATM velocity breach: {window_count} withdrawals within 1-hour window — possible card cloning or coordinated fraud."
            if velocity_breach else
            "ATM withdrawal frequency within normal limits."
        )

        return (
            "ATM VELOCITY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  ATM Withdrawals 24h  : {count_24h}\n"
            f"  Velocity Breach      : {'Yes — ALERT' if velocity_breach else 'No'}\n"
            f"  Risk Level           : {risk_level}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_atm_velocity failed: {exc}")
        return f"ATM VELOCITY REPORT\n  Error: {exc}\n  Risk Level: LOW"
    finally:
        db.close()


# ── Tool 13 — ATM Geovelocity (ATM only) ─────────────────────────────────────

@tool
def evaluate_atm_geovelocity(customer_id: str, transaction_date: str, transaction_time: str, location: str) -> str:
    """Check for ATM withdrawals at impossible geographic distances within short time windows.
    Use only for ATM transactions."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        if not _is_location_known(location):
            return (
                "ATM GEOVELOCITY REPORT\n"
                f"  Customer ID          : {customer_id}\n"
                "  Impossible Travel    : No\n"
                "  Assessment           : Insufficient location data — check skipped."
            )

        try:
            curr_dt_str = f"{transaction_date} {transaction_time}"
            curr_dt = datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M") if len(transaction_time.split(":")) == 2 \
                else datetime.strptime(curr_dt_str, "%Y-%m-%d %H:%M:%S")
            curr_dt = curr_dt.replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)

        window_start = curr_dt - timedelta(hours=4)

        _ATM_TYPES = {"atm", "atm cash", "atm withdrawal", "cash withdrawal"}
        atm_txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.transaction_date >= window_start,
                Transaction.transaction_date <= curr_dt,
            ).all()
            if (t.transaction_type or "").lower() in _ATM_TYPES
        ]

        impossible_travel = False
        conflict_location = None
        conflict_diff_mins = 0.0

        for t in atm_txns:
            if not _is_location_known(t.location):
                continue
            if not _same_city(location, t.location):
                t_dt = t.transaction_date
                if t_dt.tzinfo is None:
                    t_dt = t_dt.replace(tzinfo=timezone.utc)
                diff_mins = abs((curr_dt - t_dt).total_seconds()) / 60
                if diff_mins <= 120:
                    impossible_travel = True
                    conflict_location = t.location
                    conflict_diff_mins = round(diff_mins, 1)
                    break

        return (
            "ATM GEOVELOCITY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Current ATM Location : {location}\n"
            f"  Impossible Travel    : {'Yes — ALERT' if impossible_travel else 'No'}\n"
            + (f"  Conflict ATM Location: {conflict_location}\n"
               f"  Time Difference      : {conflict_diff_mins} minutes\n" if impossible_travel else "") +
            f"  ATM Geo Risk         : {'HIGH' if impossible_travel else 'LOW'}\n"
            f"  Assessment           : {'Impossible physical movement between two ATM locations detected.' if impossible_travel else 'ATM withdrawal locations are geographically consistent.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_atm_geovelocity failed: {exc}")
        return f"ATM GEOVELOCITY REPORT\n  Error: {exc}\n  ATM Geo Risk: LOW"
    finally:
        db.close()


# ── Tool 14 — Cash Withdrawal Patterns (ATM only) ────────────────────────────

@tool
def analyze_cash_withdrawal_patterns(customer_id: str, amount: float) -> str:
    """Analyze cash withdrawal patterns against customer's ATM withdrawal history.
    Flags unusually large or repeated withdrawals.
    Use only for ATM transactions."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        _ATM_TYPES = {"atm", "atm cash", "atm withdrawal", "cash withdrawal"}
        hist_txns = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper()
            ).order_by(Transaction.transaction_date.desc()).limit(30).all()
            if (t.transaction_type or "").lower() in _ATM_TYPES
        ]

        avg_withdrawal = sum(t.amount for t in hist_txns) / len(hist_txns) if hist_txns else amount
        large_withdrawal = amount > (avg_withdrawal * 3) if avg_withdrawal > 0 else False

        exclude_id = _active_case_id.get()
        cutoff_dt = None
        if exclude_id:
            curr = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if curr and curr.created_at:
                cutoff_dt = curr.created_at

        now = cutoff_dt or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        day_limit = now - timedelta(days=1)

        recent_atm = [
            t for t in db.query(Transaction).filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.transaction_date >= day_limit,
                Transaction.transaction_date <= now,
            ).all()
            if (t.transaction_type or "").lower() in _ATM_TYPES
        ]
        repeated_withdrawal = len(recent_atm) >= 3

        risk = "HIGH" if (large_withdrawal and repeated_withdrawal) else "MEDIUM" if (large_withdrawal or repeated_withdrawal) else "LOW"
        flags = []
        if large_withdrawal:
            flags.append(f"Amount {amount:,.2f} is {amount/avg_withdrawal:.1f}x above ATM average ({avg_withdrawal:,.2f})")
        if repeated_withdrawal:
            flags.append(f"{len(recent_atm)} ATM withdrawals in last 24h")

        return (
            "CASH WITHDRAWAL PATTERN REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  This Withdrawal      : {amount:,.2f}\n"
            f"  Avg ATM Withdrawal   : {avg_withdrawal:,.2f}\n"
            f"  Large Withdrawal     : {'Yes — ALERT' if large_withdrawal else 'No'}\n"
            f"  Repeated Withdrawal  : {'Yes — ALERT' if repeated_withdrawal else 'No'}\n"
            f"  ATM Count 24h        : {len(recent_atm)}\n"
            f"  Risk Level           : {risk}\n"
            f"  Flags                : {' | '.join(flags) if flags else 'None'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_cash_withdrawal_patterns failed: {exc}")
        return f"CASH WITHDRAWAL PATTERN REPORT\n  Error: {exc}\n  Risk Level: LOW"
    finally:
        db.close()


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    # Core tools — used by digital channel
    "detect_transaction_anomalies":       detect_transaction_anomalies,
    "evaluate_location_velocity":         evaluate_location_velocity,
    "analyze_spending_behavior":          analyze_spending_behavior,
    "verify_kyc_match":                   verify_kyc_match,
    "evaluate_device_fingerprint":        evaluate_device_fingerprint,
    "analyze_behavioral_patterns":        analyze_behavioral_patterns,
    # All channels
    "evaluate_merchant_risk_intelligence": evaluate_merchant_risk_intelligence,
    # Card POS channel
    "analyze_card_velocity":              analyze_card_velocity,
    "evaluate_atm_pos_distance":          evaluate_atm_pos_distance,
    "analyze_foreign_usage":              analyze_foreign_usage,
    "analyze_card_present_anomalies":     analyze_card_present_anomalies,
    # ATM channel
    "analyze_atm_velocity":               analyze_atm_velocity,
    "evaluate_atm_geovelocity":           evaluate_atm_geovelocity,
    "analyze_cash_withdrawal_patterns":   analyze_cash_withdrawal_patterns,
}
