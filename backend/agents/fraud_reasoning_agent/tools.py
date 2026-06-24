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


# ── GPS Haversine helper ───────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km between two GPS coordinates."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Speed thresholds (km/h)
_SPEED_MEDIUM       = 150   # unusually fast ground travel — worth flagging
_SPEED_HIGH         = 500   # only achievable by aircraft — strong signal
_SPEED_CRITICAL     = 900   # faster than commercial aircraft — physically impossible


# ── Tool 2 — Location Velocity (GPS-based Geovelocity) ────────────────────────

@tool
def evaluate_location_velocity(customer_id: str, location: str, transaction_date: str, transaction_time: str) -> str:
    """Evaluates geographic velocity using GPS coordinates (latitude/longitude) stored in
    the transaction database. Calculates actual distance and implied travel speed between
    consecutive transactions. Flags physically impossible or highly suspicious travel speeds.
    Use this to detect card cloning, account takeover, and simultaneous multi-location fraud."""
    from database.database import SessionLocal
    from database.models import Transaction, DisputeCase

    db = SessionLocal()
    try:
        # Parse current transaction datetime
        try:
            curr_dt_str = f"{transaction_date} {transaction_time}"
            curr_dt = datetime.strptime(
                curr_dt_str,
                "%Y-%m-%d %H:%M" if len(transaction_time.split(":")) == 2 else "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)

        # Get current transaction's GPS coords from DB
        exclude_id = _active_case_id.get()
        curr_case  = None
        curr_lat   = None
        curr_lon   = None
        curr_txn_id = None

        if exclude_id:
            curr_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
        if curr_case:
            curr_txn_id = curr_case.transaction_id
            curr_txn = db.query(Transaction).filter(
                Transaction.transaction_id == curr_txn_id
            ).first()
            if curr_txn:
                curr_lat = curr_txn.latitude
                curr_lon = curr_txn.longitude

        if curr_lat is None or curr_lon is None:
            return (
                "GEOGRAPHIC VELOCITY REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Geovelocity Risk : LOW\n"
                "  Geovelocity Breach: No\n"
                "  Assessment       : No GPS coordinates on this transaction — geovelocity check skipped."
            )

        # Query all other transactions for this customer that have GPS data
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.customer_id == customer_id.upper(),
                Transaction.latitude    != None,
                Transaction.longitude   != None,
            )
            .order_by(Transaction.transaction_date.desc())
            .all()
        )

        if not txns:
            return (
                "GEOGRAPHIC VELOCITY REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Geovelocity Risk : LOW\n"
                "  Assessment       : No GPS-tagged transaction history found."
            )

        geovelocity_breach = False
        conflict_txn       = None
        conflict_speed_kmh = 0.0
        conflict_dist_km   = 0.0
        time_diff_hours    = 0.0
        risk               = "LOW"

        for t in txns:
            if curr_txn_id and t.transaction_id == curr_txn_id:
                continue
            if t.latitude is None or t.longitude is None:
                continue

            t_dt = t.transaction_date
            if t_dt.tzinfo is None:
                t_dt = t_dt.replace(tzinfo=timezone.utc)

            diff_hours = abs((curr_dt - t_dt).total_seconds()) / 3600.0
            if diff_hours < 0.001:   # same second — skip
                continue

            dist_km   = _haversine_km(curr_lat, curr_lon, t.latitude, t.longitude)
            speed_kmh = dist_km / diff_hours

            # Only flag if locations are meaningfully different (> 5 km)
            if dist_km < 5:
                continue

            if speed_kmh >= _SPEED_CRITICAL:
                geovelocity_breach = True
                risk = "CRITICAL"
                conflict_txn       = t
                conflict_speed_kmh = round(speed_kmh, 0)
                conflict_dist_km   = round(dist_km, 1)
                time_diff_hours    = round(diff_hours, 2)
                break   # worst case found — stop scanning
            elif speed_kmh >= _SPEED_HIGH and risk != "CRITICAL":
                geovelocity_breach = True
                risk = "HIGH"
                conflict_txn       = t
                conflict_speed_kmh = round(speed_kmh, 0)
                conflict_dist_km   = round(dist_km, 1)
                time_diff_hours    = round(diff_hours, 2)
                # Keep scanning — might find CRITICAL
            elif speed_kmh >= _SPEED_MEDIUM and risk not in ("CRITICAL", "HIGH"):
                geovelocity_breach = True
                risk = "MEDIUM"
                conflict_txn       = t
                conflict_speed_kmh = round(speed_kmh, 0)
                conflict_dist_km   = round(dist_km, 1)
                time_diff_hours    = round(diff_hours, 2)
                # Keep scanning — might find HIGH or CRITICAL

        if geovelocity_breach and conflict_txn:
            verdict = "impossible" if risk == "CRITICAL" else "highly suspicious"
            assessment = (
                f"{verdict.capitalize()} travel speed detected: {conflict_dist_km} km in "
                f"{time_diff_hours}h = {conflict_speed_kmh} km/h. "
                f"Current: {location} ({curr_lat:.4f},{curr_lon:.4f}) — "
                f"Previous: {conflict_txn.location} ({conflict_txn.latitude:.4f},{conflict_txn.longitude:.4f})."
            )
            conflict_info = (
                f"  Conflict Location    : {conflict_txn.location}\n"
                f"  Conflict GPS         : {conflict_txn.latitude:.4f}, {conflict_txn.longitude:.4f}\n"
                f"  Distance (km)        : {conflict_dist_km}\n"
                f"  Time Difference (Hrs): {time_diff_hours}\n"
                f"  Implied Speed (km/h) : {conflict_speed_kmh}\n"
            )
        else:
            assessment = "All transaction locations are geographically consistent with plausible travel speeds."
            conflict_info = ""

        return (
            "GEOGRAPHIC VELOCITY REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Current Location     : {location}\n"
            f"  Current GPS          : {curr_lat:.4f}, {curr_lon:.4f}\n"
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

        # Check velocity: deduplicate by case_id before counting (live + history can overlap)
        seen_ids: set = set()
        all_dates = []
        for c in hist_cases + live_cases:
            cid_key = getattr(c, "case_id", None)
            if cid_key and cid_key in seen_ids:
                continue
            if cid_key:
                seen_ids.add(cid_key)
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


# ── Card POS Advanced Intelligence Tools ─────────────────────────────────────

@tool
def detect_merchant_compromise_pattern(case_id: str) -> str:
    """Detect if the disputed merchant has an abnormal dispute spike in the last 7-30 days,
    indicating a possible merchant compromise or skimming device installation."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory, MerchantProfile
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "MERCHANT COMPROMISE PATTERN\n  Error: Case not found\n  Risk Level: LOW"

        merchant_name = case.merchant or ""
        now = datetime.now(timezone.utc)
        w7  = now - timedelta(days=7)
        w30 = now - timedelta(days=30)

        hist_7d  = db.query(DisputeHistory).filter(
            DisputeHistory.merchant_id.ilike(f"%{merchant_name}%") |
            DisputeHistory.dispute_category.isnot(None),
            DisputeHistory.created_at >= w7,
        ).all()
        # Filter by merchant name in dispute records
        hist_7d  = [h for h in hist_7d if merchant_name.lower() in (h.merchant_id or "").lower()] if merchant_name else []

        hist_30d = db.query(DisputeHistory).filter(
            DisputeHistory.created_at >= w30,
        ).all()
        hist_30d = [h for h in hist_30d if merchant_name.lower() in (h.merchant_id or "").lower()] if merchant_name else []

        recent_7d  = len(hist_7d)
        recent_30d = len(hist_30d)
        affected   = len(set(h.customer_id for h in hist_30d))

        mp = db.query(MerchantProfile).filter(
            MerchantProfile.merchant_name.ilike(f"%{merchant_name}%")
        ).first()

        total_txns   = (mp.total_transactions or 1) if mp else 1
        dispute_rate = round(recent_30d / total_txns * 100, 2)

        compromise_detected = recent_7d >= 10 or affected >= 5 or dispute_rate > 15.0
        if recent_7d >= 20 or affected >= 15:
            risk = "CRITICAL"
        elif compromise_detected:
            risk = "HIGH"
        else:
            risk = "LOW"

        return (
            "MERCHANT COMPROMISE PATTERN REPORT\n"
            f"  Merchant             : {merchant_name}\n"
            f"  7-Day Disputes       : {recent_7d}\n"
            f"  30-Day Disputes      : {recent_30d}\n"
            f"  Affected Customers   : {affected}\n"
            f"  Dispute Rate (30d)   : {dispute_rate}%\n"
            f"  Compromise Detected  : {'Yes — ALERT' if compromise_detected else 'No'}\n"
            f"  Risk Level           : {risk}\n"
            f"  Assessment           : {'Abnormal dispute spike — possible merchant compromise or skimming device.' if compromise_detected else 'Dispute volume within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_merchant_compromise_pattern failed: {exc}")
        return f"MERCHANT COMPROMISE PATTERN REPORT\n  Error: {exc}\n  Risk Level: LOW"
    finally:
        db.close()


@tool
def analyze_first_time_merchant(case_id: str) -> str:
    """Determine if the customer has ever transacted with this merchant before.
    First-time high-value transactions at unfamiliar merchants are a key card fraud signal."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from sqlalchemy import func

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "FIRST-TIME MERCHANT ANALYSIS\n  Error: Case not found\n  High Value First Time: No"

        customer_id  = (case.customer_id or "").upper()
        merchant     = case.merchant or ""
        amount       = float(case.amount or 0)
        txn_id       = case.transaction_id or ""

        prior_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
            func.lower(Transaction.merchant_name).contains(merchant.lower()),
            Transaction.transaction_id != txn_id,
        ).all()
        prior_count = len(prior_txns)
        first_time  = prior_count == 0

        all_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
        ).order_by(Transaction.transaction_date.desc()).limit(30).all()
        avg_amount = sum(t.amount for t in all_txns) / max(len(all_txns), 1)

        high_value_first_time = first_time and amount > avg_amount * 1.5

        return (
            "FIRST-TIME MERCHANT ANALYSIS\n"
            f"  Merchant             : {merchant}\n"
            f"  Prior Transactions   : {prior_count}\n"
            f"  First Time           : {'Yes' if first_time else 'No'}\n"
            f"  Transaction Amount   : {amount:,.2f}\n"
            f"  Customer Average     : {avg_amount:,.2f}\n"
            f"  High Value First Time: {'Yes — ALERT' if high_value_first_time else 'No'}\n"
            f"  Assessment           : {'No prior history with merchant at high value — card fraud indicator.' if high_value_first_time else 'Prior merchant relationship exists or amount is within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_first_time_merchant failed: {exc}")
        return f"FIRST-TIME MERCHANT ANALYSIS\n  Error: {exc}\n  High Value First Time: No"
    finally:
        db.close()


@tool
def evaluate_merchant_resolution_history(case_id: str) -> str:
    """Evaluate merchant dispute resolution history to identify merchants where
    customers frequently win disputes, indicating merchant fault patterns."""
    from database.database import SessionLocal
    from database.models import DisputeCase, MerchantProfile

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "MERCHANT RESOLUTION HISTORY\n  Error: Case not found\n  Merchant Dispute Risk: LOW"

        merchant = case.merchant or ""
        mp = db.query(MerchantProfile).filter(
            MerchantProfile.merchant_name.ilike(f"%{merchant}%")
        ).first()

        if not mp:
            return (
                "MERCHANT RESOLUTION HISTORY\n"
                f"  Merchant             : {merchant}\n"
                "  Status               : Not in merchant profiles\n"
                "  Customer Favor Rate  : N/A\n"
                "  Merchant Dispute Risk: LOW"
            )

        cust_favor   = mp.resolved_customer_favor or 0
        merch_favor  = mp.resolved_merchant_favor or 0
        total_res    = cust_favor + merch_favor
        cust_rate    = (cust_favor / max(total_res, 1)) * 100

        if cust_rate > 85:
            risk = "CRITICAL"
        elif cust_rate > 70:
            risk = "HIGH"
        elif cust_rate > 50:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return (
            "MERCHANT RESOLUTION HISTORY\n"
            f"  Merchant             : {mp.merchant_name}\n"
            f"  Total Resolved       : {total_res}\n"
            f"  Customer Favor Count : {cust_favor}\n"
            f"  Merchant Favor Count : {merch_favor}\n"
            f"  Customer Favor Rate  : {cust_rate:.1f}%\n"
            f"  Merchant Dispute Risk: {risk}\n"
            f"  Assessment           : {'Very high customer win rate — merchant likely at fault.' if risk in ('CRITICAL','HIGH') else 'Dispute resolution pattern within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_merchant_resolution_history failed: {exc}")
        return f"MERCHANT RESOLUTION HISTORY\n  Error: {exc}\n  Merchant Dispute Risk: LOW"
    finally:
        db.close()


@tool
def detect_card_testing_pattern(case_id: str) -> str:
    """Detect card testing activity — fraudsters make small micro-transactions
    (INR 1-50) to verify a stolen card before making large fraudulent purchases."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "CARD TESTING PATTERN REPORT\n  Error: Case not found\n  Card Testing Detected: No"

        customer_id = (case.customer_id or "").upper()
        txn_date    = case.transaction_date
        if isinstance(txn_date, str):
            try:
                txn_date = datetime.fromisoformat(txn_date)
            except Exception:
                txn_date = datetime.now(timezone.utc)
        if txn_date and txn_date.tzinfo is None:
            txn_date = txn_date.replace(tzinfo=timezone.utc)
        window_start = (txn_date or datetime.now(timezone.utc)) - timedelta(hours=24)

        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
            Transaction.transaction_date >= window_start,
            Transaction.amount <= 50,
            Transaction.status.in_(["Success", "Pending"]),
        ).order_by(Transaction.transaction_date).all()

        test_count = len(txns)
        card_testing = test_count >= 3

        time_window = ""
        if card_testing and len(txns) >= 2:
            t1 = txns[0].transaction_date
            t2 = txns[-1].transaction_date
            if t1 and t2:
                if t1.tzinfo is None: t1 = t1.replace(tzinfo=timezone.utc)
                if t2.tzinfo is None: t2 = t2.replace(tzinfo=timezone.utc)
                mins = round(abs((t2 - t1).total_seconds()) / 60, 1)
                time_window = f"{mins} minutes"

        return (
            "CARD TESTING PATTERN REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Micro-Txn Count (<=50): {test_count}\n"
            f"  Card Testing Detected: {'Yes — ALERT' if card_testing else 'No'}\n"
            + (f"  Test Window          : {time_window}\n" if time_window else "") +
            f"  Assessment           : {'Multiple micro-transactions detected — classic card verification pattern before large fraud.' if card_testing else 'No card testing activity detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_card_testing_pattern failed: {exc}")
        return f"CARD TESTING PATTERN REPORT\n  Error: {exc}\n  Card Testing Detected: No"
    finally:
        db.close()


@tool
def analyze_multi_merchant_burst(case_id: str) -> str:
    """Detect rapid merchant-hopping — a stolen card pattern where fraudsters
    quickly visit multiple merchants to maximize value before the card is blocked."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "MULTI-MERCHANT BURST REPORT\n  Error: Case not found\n  Merchant Burst Detected: No"

        customer_id = (case.customer_id or "").upper()
        txn_date    = case.transaction_date
        if isinstance(txn_date, str):
            try:
                txn_date = datetime.fromisoformat(txn_date)
            except Exception:
                txn_date = datetime.now(timezone.utc)
        if txn_date and txn_date.tzinfo is None:
            txn_date = txn_date.replace(tzinfo=timezone.utc)
        window_start = (txn_date or datetime.now(timezone.utc)) - timedelta(hours=2)

        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
            Transaction.transaction_date >= window_start,
        ).order_by(Transaction.transaction_date).all()

        unique_merchants = len(set(t.merchant_name for t in txns if t.merchant_name))
        duration_minutes = 0.0
        if len(txns) >= 2:
            t1 = txns[0].transaction_date
            t2 = txns[-1].transaction_date
            if t1 and t2:
                if t1.tzinfo is None: t1 = t1.replace(tzinfo=timezone.utc)
                if t2.tzinfo is None: t2 = t2.replace(tzinfo=timezone.utc)
                duration_minutes = round(abs((t2 - t1).total_seconds()) / 60, 1)

        burst_detected = unique_merchants >= 4 and duration_minutes <= 30

        return (
            "MULTI-MERCHANT BURST REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Transactions (2h)    : {len(txns)}\n"
            f"  Unique Merchants     : {unique_merchants}\n"
            f"  Duration (minutes)   : {duration_minutes}\n"
            f"  Merchant Burst Detected: {'Yes — ALERT' if burst_detected else 'No'}\n"
            f"  Assessment           : {'Rapid merchant hopping detected — consistent with stolen card fraud pattern.' if burst_detected else 'Transaction sequence within normal merchant usage patterns.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_multi_merchant_burst failed: {exc}")
        return f"MULTI-MERCHANT BURST REPORT\n  Error: {exc}\n  Merchant Burst Detected: No"
    finally:
        db.close()


@tool
def evaluate_mcc_risk(case_id: str) -> str:
    """Score the merchant category risk level for card fraud.
    Certain merchant categories have significantly higher card fraud rates."""
    from database.database import SessionLocal
    from database.models import DisputeCase, MerchantProfile

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "MCC RISK ANALYSIS\n  Error: Case not found\n  Category Risk Level: LOW"

        merchant_name = (case.merchant or "").lower()

        mp = db.query(MerchantProfile).filter(
            MerchantProfile.merchant_name.ilike(f"%{case.merchant}%")
        ).first()

        category = (mp.merchant_category or "").lower() if mp else ""

        _CRITICAL = {"crypto", "gift card", "gaming credits", "virtual currency", "prepaid card"}
        _HIGH     = {"electronics", "jewellery", "jewelry", "gaming", "travel", "airline",
                     "luxury", "forex", "digital goods", "online marketplace", "money transfer"}
        _LOW      = {"grocery", "pharmacy", "fuel", "petrol", "utilities", "hospital",
                     "medical", "supermarket", "bakery", "restaurant"}

        def _match(word_set: set, text: str) -> bool:
            return any(w in text for w in word_set)

        combined = f"{category} {merchant_name}"
        if _match(_CRITICAL, combined):
            risk = "CRITICAL"
            ctx  = "Highest-risk merchant category — crypto/gift cards are primary targets for card fraud."
        elif _match(_HIGH, combined):
            risk = "HIGH"
            ctx  = "High-risk merchant category — electronics, travel, and luxury goods are frequent card fraud targets."
        elif _match(_LOW, combined):
            risk = "LOW"
            ctx  = "Low-risk merchant category — everyday essential purchases show low fraud rates."
        else:
            risk = "MEDIUM"
            ctx  = "Moderate-risk merchant category."

        return (
            "MCC RISK ANALYSIS\n"
            f"  Merchant             : {case.merchant}\n"
            f"  Merchant Category    : {mp.merchant_category if mp else 'Unknown'}\n"
            f"  Category Risk Level  : {risk}\n"
            f"  Assessment           : {ctx}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_mcc_risk failed: {exc}")
        return f"MCC RISK ANALYSIS\n  Error: {exc}\n  Category Risk Level: LOW"
    finally:
        db.close()


@tool
def analyze_decline_success_pattern(case_id: str) -> str:
    """Detect card testing pattern: multiple declined transactions followed by
    a successful one — indicates fraudster testing stolen card details."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "DECLINE-SUCCESS PATTERN REPORT\n  Error: Case not found\n  Pattern Detected: No"

        customer_id = (case.customer_id or "").upper()
        txn_date    = case.transaction_date
        if isinstance(txn_date, str):
            try:
                txn_date = datetime.fromisoformat(txn_date)
            except Exception:
                txn_date = datetime.now(timezone.utc)
        if txn_date and txn_date.tzinfo is None:
            txn_date = txn_date.replace(tzinfo=timezone.utc)
        window_start = (txn_date or datetime.now(timezone.utc)) - timedelta(hours=24)

        txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
            Transaction.transaction_date >= window_start,
        ).order_by(Transaction.transaction_date).all()

        txn_dt = txn_date or datetime.now(timezone.utc)
        declined_before = [
            t for t in txns
            if t.status in ("Failed", "Pending") and t.transaction_date and
            (t.transaction_date.replace(tzinfo=timezone.utc) if t.transaction_date.tzinfo is None else t.transaction_date) < txn_dt
        ]
        pattern_detected = len(declined_before) >= 2

        return (
            "DECLINE-SUCCESS PATTERN REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Total Transactions (24h): {len(txns)}\n"
            f"  Declined Attempts    : {len(declined_before)}\n"
            f"  Pattern Detected     : {'Yes — ALERT' if pattern_detected else 'No'}\n"
            f"  Assessment           : {'Multiple declined attempts before success — card testing pattern detected.' if pattern_detected else 'No anomalous decline pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_decline_success_pattern failed: {exc}")
        return f"DECLINE-SUCCESS PATTERN REPORT\n  Error: {exc}\n  Pattern Detected: No"
    finally:
        db.close()


@tool
def check_refund_reversal_absence(case_id: str) -> str:
    """Verify refund/reversal claims by checking if a corresponding reversal
    transaction exists in records. Unverified refund claims indicate fraud."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "REFUND REVERSAL ANALYSIS\n  Error: Case not found\n  Refund Claim Unverified: No"

        category = (case.dispute_category or "").lower()
        if "refund" not in category and "reversal" not in category:
            return (
                "REFUND REVERSAL ANALYSIS\n"
                f"  Dispute Category     : {case.dispute_category or 'N/A'}\n"
                "  Not applicable — dispute is not a refund claim.\n"
                "  Refund Claim Unverified: No"
            )

        customer_id  = (case.customer_id or "").upper()
        merchant     = case.merchant or ""
        amount       = float(case.amount or 0)
        window_start = datetime.now(timezone.utc) - timedelta(days=60)

        reversals = db.query(Transaction).filter(
            Transaction.customer_id == customer_id,
            func.lower(Transaction.merchant_name).contains(merchant.lower()),
            Transaction.status == "Reversed",
            Transaction.transaction_date >= window_start,
        ).all()

        reversal_found       = len(reversals) > 0
        refund_claim_unverif = not reversal_found

        return (
            "REFUND REVERSAL ANALYSIS\n"
            f"  Merchant             : {merchant}\n"
            f"  Claimed Amount       : {amount:,.2f}\n"
            f"  Reversal Txns Found  : {len(reversals)}\n"
            f"  Refund Claim Unverified: {'Yes — ALERT' if refund_claim_unverif else 'No'}\n"
            f"  Assessment           : {'No reversal transaction found — refund claim cannot be verified.' if refund_claim_unverif else 'Reversal transaction confirmed in records.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"check_refund_reversal_absence failed: {exc}")
        return f"REFUND REVERSAL ANALYSIS\n  Error: {exc}\n  Refund Claim Unverified: No"
    finally:
        db.close()


# ── UPI Fraud Intelligence Tools ──────────────────────────────────────────────

@tool
def analyze_new_beneficiary_risk(case_id: str) -> str:
    """Detect large UPI transfers to beneficiaries the customer has never previously used."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "NEW BENEFICIARY RISK\n  New Beneficiary Risk: No\n  Assessment: Case not found."
        customer_id = case.customer_id or ""
        merchant = case.merchant or ""
        amount = float(case.amount or 0)
        prior = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.merchant_name.ilike(f"%{merchant}%"),
            Transaction.transaction_id != (case.transaction_id or ""),
        ).all()
        prior_count = len(prior)
        new_beneficiary = prior_count == 0
        all_txns = db.query(Transaction).filter(Transaction.customer_id == customer_id.upper()).order_by(Transaction.transaction_date.desc()).limit(30).all()
        avg_amount = sum(float(t.amount or 0) for t in all_txns) / max(len(all_txns), 1)
        large_transfer = amount > max(avg_amount * 2, 10000)
        new_beneficiary_risk = new_beneficiary and large_transfer
        return (
            "NEW BENEFICIARY RISK REPORT\n"
            f"  Beneficiary          : {merchant}\n"
            f"  Prior Transfers      : {prior_count}\n"
            f"  New Beneficiary      : {'Yes' if new_beneficiary else 'No'}\n"
            f"  Transaction Amount   : INR {amount:,.2f}\n"
            f"  Avg Transfer Amount  : INR {avg_amount:,.2f}\n"
            f"  Large Transfer       : {'Yes' if large_transfer else 'No'}\n"
            f"  New Beneficiary Risk : {'Yes' if new_beneficiary_risk else 'No'}\n"
            f"  Assessment           : {'High-value transfer to first-time beneficiary — strong fraud signal.' if new_beneficiary_risk else 'Beneficiary known or amount within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_new_beneficiary_risk failed: {exc}")
        return f"NEW BENEFICIARY RISK REPORT\n  Error: {exc}\n  New Beneficiary Risk: No"
    finally:
        db.close()


@tool
def detect_upi_collect_request_fraud(case_id: str) -> str:
    """Detect UPI Collect request fraud — one of India's most common UPI fraud vectors
    where fraudsters send a payment request and trick victims into approving it."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "UPI COLLECT REQUEST ANALYSIS\n  Collect Request Detected: No"
        meta = case.transaction_metadata or {}
        dispute_reason = (case.dispute_reason or "").lower()
        comment = (case.customer_comment or "").lower()
        from_meta = str(meta.get("collect_request", "")).lower() in {"yes", "true", "1"}
        from_reason = "collect" in dispute_reason
        from_comment = "collect" in comment or "money request" in comment or "payment request" in comment
        detected = from_meta or from_reason or from_comment
        method = ("transaction metadata" if from_meta else "dispute reason" if from_reason else "customer description" if from_comment else "not detected")
        return (
            "UPI COLLECT REQUEST ANALYSIS\n"
            f"  Collect Request Detected : {'Yes' if detected else 'No'}\n"
            f"  Detection Method         : {method}\n"
            f"  Assessment               : {'UPI collect request fraud detected — customer approved fraudulent payment request.' if detected else 'No collect request fraud pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_upi_collect_request_fraud failed: {exc}")
        return f"UPI COLLECT REQUEST ANALYSIS\n  Error: {exc}\n  Collect Request Detected: No"
    finally:
        db.close()


@tool
def analyze_beneficiary_velocity(case_id: str) -> str:
    """Detect suspicious beneficiary concentration — multiple customers sending to same beneficiary."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory, Transaction
    from datetime import datetime, timezone, timedelta
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "BENEFICIARY VELOCITY REPORT\n  Velocity Flag: No"
        merchant = case.merchant or ""
        now = datetime.now(timezone.utc)
        hist = db.query(DisputeHistory).filter(
            DisputeHistory.created_at >= now - timedelta(days=30),
        ).all()
        disputing_customers = {h.customer_id for h in hist if merchant.lower() in (h.merchant_id or "").lower()}
        unique_customers = len(disputing_customers)
        recent_txns = db.query(Transaction).filter(
            Transaction.merchant_name.ilike(f"%{merchant}%"),
            Transaction.transaction_date >= now - timedelta(days=7),
        ).all()
        recent_senders = len({t.customer_id for t in recent_txns})
        velocity_flag = unique_customers >= 5 or recent_senders >= 8
        risk = "HIGH" if velocity_flag else "LOW"
        return (
            "BENEFICIARY VELOCITY REPORT\n"
            f"  Beneficiary                      : {merchant}\n"
            f"  Unique Disputing Customers (30d) : {unique_customers}\n"
            f"  Recent Unique Senders (7d)       : {recent_senders}\n"
            f"  Velocity Flag                    : {'Yes' if velocity_flag else 'No'}\n"
            f"  Risk Level                       : {risk}\n"
            f"  Assessment                       : {'Multiple customers disputing this beneficiary — possible fraud hub.' if velocity_flag else 'Beneficiary activity within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_beneficiary_velocity failed: {exc}")
        return f"BENEFICIARY VELOCITY REPORT\n  Error: {exc}\n  Velocity Flag: No"
    finally:
        db.close()


@tool
def evaluate_upi_handle_reputation(case_id: str) -> str:
    """Evaluate UPI handle/beneficiary reputation using historical dispute data."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "UPI HANDLE REPUTATION\n  UPI Handle Reputation: LOW_RISK"
        merchant = case.merchant or ""
        all_hist = db.query(DisputeHistory).all()
        matching = [h for h in all_hist if merchant.lower() in (h.merchant_id or "").lower() or merchant.lower() in (getattr(h, 'merchant_name', '') or "").lower()]
        total_disputes = len(matching)
        fraud_reports = sum(1 for h in matching if h.fraud_claim)
        fraud_rate = fraud_reports / max(total_disputes, 1) * 100
        reputation = ("HIGH_RISK" if fraud_reports >= 5 or fraud_rate > 30
                      else "MEDIUM_RISK" if fraud_reports >= 2 or fraud_rate > 15
                      else "LOW_RISK")
        return (
            "UPI HANDLE REPUTATION REPORT\n"
            f"  Beneficiary          : {merchant}\n"
            f"  Total Disputes       : {total_disputes}\n"
            f"  Fraud Reports        : {fraud_reports}\n"
            f"  Fraud Rate           : {fraud_rate:.1f}%\n"
            f"  UPI Handle Reputation: {reputation}\n"
            f"  Assessment           : {'Known high-risk beneficiary with significant fraud history.' if reputation == 'HIGH_RISK' else 'Moderate dispute history.' if reputation == 'MEDIUM_RISK' else 'No significant fraud history for this beneficiary.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_upi_handle_reputation failed: {exc}")
        return f"UPI HANDLE REPUTATION REPORT\n  Error: {exc}\n  UPI Handle Reputation: LOW_RISK"
    finally:
        db.close()


@tool
def analyze_dormant_beneficiary_risk(case_id: str) -> str:
    """Detect transfers to recently-created beneficiaries — fraudsters register new accounts
    immediately before receiving stolen funds."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "DORMANT BENEFICIARY RISK\n  Dormant Risk: No"
        customer_id = case.customer_id or ""
        merchant = case.merchant or ""
        prior_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.merchant_name.ilike(f"%{merchant}%"),
            Transaction.transaction_id != (case.transaction_id or ""),
        ).order_by(Transaction.transaction_date.asc()).all()
        if not prior_txns:
            beneficiary_age_days = 0
            dormant_risk = True
            first_date_str = "First transaction (no prior history)"
        else:
            from datetime import timezone as _tz
            first_dt = prior_txns[0].transaction_date
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(tzinfo=_tz.utc)
            try:
                from datetime import datetime
                txn_dt_str = f"{case.transaction_date or ''} {case.transaction_time or ''}".strip()
                txn_dt = datetime.strptime(txn_dt_str, "%Y-%m-%d %H:%M") if txn_dt_str else datetime.now(_tz.utc)
                if txn_dt.tzinfo is None:
                    txn_dt = txn_dt.replace(tzinfo=_tz.utc)
            except Exception:
                from datetime import datetime
                txn_dt = datetime.now(_tz.utc)
            beneficiary_age_days = (txn_dt - first_dt).days
            dormant_risk = beneficiary_age_days < 7
            first_date_str = first_dt.strftime("%Y-%m-%d")
        return (
            "DORMANT BENEFICIARY RISK REPORT\n"
            f"  Beneficiary          : {merchant}\n"
            f"  First Transaction    : {first_date_str}\n"
            f"  Beneficiary Age      : {beneficiary_age_days} days\n"
            f"  Dormant Risk         : {'Yes' if dormant_risk else 'No'}\n"
            f"  Assessment           : {'Very new beneficiary — possible freshly-created fraud account.' if dormant_risk else 'Beneficiary has established transaction history.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_dormant_beneficiary_risk failed: {exc}")
        return f"DORMANT BENEFICIARY RISK REPORT\n  Error: {exc}\n  Dormant Risk: No"
    finally:
        db.close()


# ── Internet / Mobile Banking Fraud Intelligence Tools ─────────────────────────

@tool
def detect_impossible_login_travel(case_id: str) -> str:
    """Detect impossible login/transaction travel — login from distant location within
    impossibly short time suggests account compromise."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "IMPOSSIBLE LOGIN TRAVEL\n  Impossible Travel: No"
        customer_id = case.customer_id or ""
        meta = case.transaction_metadata or {}
        current_location = meta.get("transaction_location") or ""
        try:
            txn_dt_str = f"{case.transaction_date or ''} {case.transaction_time or ''}".strip()
            curr_dt = datetime.strptime(txn_dt_str, "%Y-%m-%d %H:%M") if txn_dt_str else datetime.now(timezone.utc)
            if curr_dt.tzinfo is None:
                curr_dt = curr_dt.replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)
        window_start = curr_dt - timedelta(hours=2)
        recent_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_date >= window_start,
            Transaction.transaction_id != (case.transaction_id or ""),
        ).order_by(Transaction.transaction_date.desc()).limit(5).all()
        impossible_travel = False
        conflict_location = ""
        time_diff_str = ""
        if _is_location_known(current_location):
            for t in recent_txns:
                if _is_location_known(t.location or "") and not _same_city(current_location, t.location or ""):
                    t_dt = t.transaction_date
                    if t_dt.tzinfo is None:
                        t_dt = t_dt.replace(tzinfo=timezone.utc)
                    diff_h = abs((curr_dt - t_dt).total_seconds()) / 3600
                    if diff_h < 2:
                        impossible_travel = True
                        conflict_location = t.location or ""
                        time_diff_str = f"{round(diff_h * 60)} minutes"
                        break
        return (
            "IMPOSSIBLE LOGIN TRAVEL REPORT\n"
            f"  Current Location     : {current_location or 'Not provided'}\n"
            f"  Conflicting Location : {conflict_location or 'None'}\n"
            f"  Time Difference      : {time_diff_str or 'N/A'}\n"
            f"  Impossible Travel    : {'Yes' if impossible_travel else 'No'}\n"
            f"  Assessment           : {'Impossible geographic displacement detected — strong account compromise indicator.' if impossible_travel else 'No impossible travel detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_impossible_login_travel failed: {exc}")
        return f"IMPOSSIBLE LOGIN TRAVEL REPORT\n  Error: {exc}\n  Impossible Travel: No"
    finally:
        db.close()


@tool
def analyze_device_change_large_transfer(case_id: str) -> str:
    """Detect large transfers made immediately after a device change — common ATO pattern."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "DEVICE CHANGE TRANSFER ANALYSIS\n  Risk Detected: No"
        customer_id = case.customer_id or ""
        meta = case.transaction_metadata or {}
        current_device = meta.get("device_id") or ""
        amount = float(case.amount or 0)
        prior_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_id != (case.transaction_id or ""),
        ).order_by(Transaction.transaction_date.desc()).limit(10).all()
        prior_devices = {t.device_id for t in prior_txns if t.device_id}
        device_changed = bool(current_device and prior_devices and current_device not in prior_devices)
        avg_amount = sum(float(t.amount or 0) for t in prior_txns) / max(len(prior_txns), 1)
        large_transfer = amount > max(avg_amount * 2, 25000)
        risk_detected = device_changed and large_transfer
        return (
            "DEVICE CHANGE TRANSFER ANALYSIS\n"
            f"  Current Device       : {current_device or 'Not provided'}\n"
            f"  Prior Devices (count): {len(prior_devices)}\n"
            f"  Device Changed       : {'Yes' if device_changed else 'No'}\n"
            f"  Transaction Amount   : INR {amount:,.2f}\n"
            f"  Average Amount       : INR {avg_amount:,.2f}\n"
            f"  Large Transfer       : {'Yes' if large_transfer else 'No'}\n"
            f"  Risk Detected        : {'Yes' if risk_detected else 'No'}\n"
            f"  Assessment           : {'Large transfer immediately after device change — account takeover indicator.' if risk_detected else 'No device change risk detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_device_change_large_transfer failed: {exc}")
        return f"DEVICE CHANGE TRANSFER ANALYSIS\n  Error: {exc}\n  Risk Detected: No"
    finally:
        db.close()


@tool
def detect_password_reset_transaction_pattern(case_id: str) -> str:
    """Detect transactions immediately following password resets — classic ATO indicator."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "PASSWORD RESET PATTERN\n  Pattern Detected: No"
        meta = case.transaction_metadata or {}
        password_reset = str(meta.get("password_reset_before", "")).lower() in {"yes", "true", "1"}
        return (
            "PASSWORD RESET PATTERN REPORT\n"
            f"  Password Reset Before Transaction: {'Yes' if password_reset else 'No'}\n"
            f"  Pattern Detected                 : {'Yes' if password_reset else 'No'}\n"
            f"  Assessment                       : {'Transaction followed password reset — high-risk ATO pattern.' if password_reset else 'No password reset pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_password_reset_transaction_pattern failed: {exc}")
        return f"PASSWORD RESET PATTERN REPORT\n  Error: {exc}\n  Pattern Detected: No"
    finally:
        db.close()


@tool
def analyze_mobile_number_change_risk(case_id: str) -> str:
    """Detect transactions following mobile number changes — critical ATO signal."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "MOBILE NUMBER CHANGE RISK\n  Mobile Number Changed: No\n  ATO Risk: LOW"
        meta = case.transaction_metadata or {}
        mobile_changed = str(meta.get("mobile_number_changed", "")).lower() in {"yes", "true", "1"}
        ato_risk = "HIGH" if mobile_changed else "LOW"
        return (
            "MOBILE NUMBER CHANGE RISK REPORT\n"
            f"  Mobile Number Changed: {'Yes' if mobile_changed else 'No'}\n"
            f"  ATO Risk             : {ato_risk}\n"
            f"  Assessment           : {'Mobile number changed before transaction — OTP/2FA compromise risk.' if mobile_changed else 'No mobile number change detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_mobile_number_change_risk failed: {exc}")
        return f"MOBILE NUMBER CHANGE RISK REPORT\n  Error: {exc}\n  Mobile Number Changed: No\n  ATO Risk: LOW"
    finally:
        db.close()


# ── ATM Fraud Intelligence Tools ───────────────────────────────────────────────

@tool
def analyze_consecutive_atm_withdrawals(case_id: str) -> str:
    """Detect repeated ATM withdrawals in short intervals — card cloning or duress indicator."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "CONSECUTIVE ATM WITHDRAWALS\n  Consecutive Pattern: No"
        customer_id = case.customer_id or ""
        try:
            txn_dt_str = f"{case.transaction_date or ''} {case.transaction_time or ''}".strip()
            curr_dt = datetime.strptime(txn_dt_str, "%Y-%m-%d %H:%M")
            if curr_dt.tzinfo is None:
                curr_dt = curr_dt.replace(tzinfo=timezone.utc)
        except Exception:
            curr_dt = datetime.now(timezone.utc)
        window_start = curr_dt - timedelta(hours=6)
        atm_txns = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_type.in_(["ATM", "ATM Cash", "Cash Withdrawal"]),
            Transaction.transaction_date >= window_start,
        ).order_by(Transaction.transaction_date.asc()).all()
        count = len(atm_txns)
        amount_pattern = False
        if count >= 2:
            amounts = [float(t.amount or 0) for t in atm_txns]
            avg_a = sum(amounts) / len(amounts)
            amount_pattern = all(abs(a - avg_a) / max(avg_a, 1) < 0.10 for a in amounts)
        consecutive = count >= 3 or (count >= 2 and amount_pattern)
        return (
            "CONSECUTIVE ATM WITHDRAWAL REPORT\n"
            f"  ATM Withdrawals (6h)  : {count}\n"
            f"  Consecutive Pattern   : {'Yes' if consecutive else 'No'}\n"
            f"  Count                 : {count}\n"
            f"  Similar Amounts       : {'Yes' if amount_pattern else 'No'}\n"
            f"  Assessment            : {'Consecutive ATM withdrawals detected — possible card cloning or forced withdrawal.' if consecutive else 'ATM withdrawal pattern within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_consecutive_atm_withdrawals failed: {exc}")
        return f"CONSECUTIVE ATM WITHDRAWAL REPORT\n  Error: {exc}\n  Consecutive Pattern: No"
    finally:
        db.close()


@tool
def analyze_foreign_atm_usage(case_id: str) -> str:
    """Detect ATM usage in foreign locations when customer normally uses domestic ATMs."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "FOREIGN ATM USAGE\n  Foreign ATM Usage: No\n  Risk Level: LOW"
        customer_id = case.customer_id or ""
        meta = case.transaction_metadata or {}
        current_location = (meta.get("transaction_location") or "").lower()
        _INDIA = {"india", "mumbai", "delhi", "bangalore", "bengaluru", "chennai", "kolkata",
                  "hyderabad", "pune", "ahmedabad", "in", "mh", "dl", "ka", "tn", "wb", "gj",
                  "up", "rj", "mp", "haryana", "hr", "pb", "punjab", "rajasthan", "gujarat"}
        def _is_india(loc: str) -> bool:
            return any(ind in loc.lower() for ind in _INDIA) if loc else True
        hist = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_type.in_(["ATM", "ATM Cash"]),
        ).order_by(Transaction.transaction_date.desc()).limit(20).all()
        domestic_count = sum(1 for t in hist if _is_india(t.location or ""))
        domestic_pct = domestic_count / max(len(hist), 1) * 100
        foreign_atm_usage = bool(current_location and not _is_india(current_location) and domestic_pct > 80)
        risk = "HIGH" if foreign_atm_usage else "LOW"
        return (
            "FOREIGN ATM USAGE REPORT\n"
            f"  Current ATM Location     : {current_location or 'Not provided'}\n"
            f"  Historical Domestic ATM %: {domestic_pct:.1f}%\n"
            f"  Foreign ATM Usage        : {'Yes' if foreign_atm_usage else 'No'}\n"
            f"  Risk Level               : {risk}\n"
            f"  Assessment               : {'Foreign ATM usage by primarily domestic customer — card cloning indicator.' if foreign_atm_usage else 'ATM usage consistent with customer location history.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_foreign_atm_usage failed: {exc}")
        return f"FOREIGN ATM USAGE REPORT\n  Error: {exc}\n  Foreign ATM Usage: No\n  Risk Level: LOW"
    finally:
        db.close()


@tool
def detect_sim_swap_atm_pattern(case_id: str) -> str:
    """Detect ATM withdrawals shortly after SIM swap — strongest ATM fraud signal."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "SIM SWAP ATM PATTERN\n  Risk Level: LOW"
        meta = case.transaction_metadata or {}
        sim_swap = str(meta.get("sim_swap_suspected", "")).lower() in {"yes", "true", "1"}
        mobile_changed = str(meta.get("mobile_number_changed", "")).lower() in {"yes", "true", "1"}
        sim_swap_detected = sim_swap or mobile_changed
        risk = "CRITICAL" if sim_swap_detected else "LOW"
        return (
            "SIM SWAP ATM PATTERN REPORT\n"
            f"  SIM Swap Suspected           : {'Yes' if sim_swap else 'No'}\n"
            f"  Mobile Number Changed        : {'Yes' if mobile_changed else 'No'}\n"
            f"  ATM Withdrawal After Swap    : {'Yes' if sim_swap_detected else 'No'}\n"
            f"  Risk Level                   : {risk}\n"
            f"  Assessment                   : {'CRITICAL: SIM swap before ATM withdrawal — OTP bypass + card fraud combination.' if sim_swap_detected else 'No SIM swap ATM pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_sim_swap_atm_pattern failed: {exc}")
        return f"SIM SWAP ATM PATTERN REPORT\n  Error: {exc}\n  Risk Level: LOW"
    finally:
        db.close()


# ── Universal Fraud Intelligence Tools ────────────────────────────────────────

@tool
def evaluate_historical_fraud_victim_score(case_id: str) -> str:
    """Determine if customer has been a previous fraud victim — repeat targeting indicator."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "HISTORICAL FRAUD VICTIM SCORE\n  Victim Score: NONE"
        customer_id = case.customer_id or ""
        prior_fraud = db.query(DisputeCase).filter(
            DisputeCase.customer_id == customer_id.upper(),
            DisputeCase.fraud_suspicion == True,
            DisputeCase.case_id != case_id,
        ).count()
        hist_fraud = db.query(DisputeHistory).filter(
            DisputeHistory.customer_id == customer_id.upper(),
            DisputeHistory.fraud_claim == True,
        ).count()
        total = prior_fraud + hist_fraud
        victim_score = "HIGH" if total >= 3 else "MEDIUM" if total >= 1 else "NONE"
        return (
            "HISTORICAL FRAUD VICTIM SCORE\n"
            f"  Prior Fraud Cases (Live) : {prior_fraud}\n"
            f"  Historical Fraud Claims  : {hist_fraud}\n"
            f"  Total Fraud History      : {total}\n"
            f"  Victim Score             : {victim_score}\n"
            f"  Assessment               : {'High repeat-fraud victim — elevated targeting risk.' if victim_score == 'HIGH' else 'Prior fraud history noted.' if victim_score == 'MEDIUM' else 'No prior fraud history.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_historical_fraud_victim_score failed: {exc}")
        return f"HISTORICAL FRAUD VICTIM SCORE\n  Error: {exc}\n  Victim Score: NONE"
    finally:
        db.close()


@tool
def detect_account_takeover_pattern(case_id: str) -> str:
    """Detect account takeover by combining ATO signals: password reset, device change,
    phone change, SIM swap — multiple signals indicate coordinated compromise."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "ACCOUNT TAKEOVER PATTERN\n  Account Takeover Risk: LOW"
        meta = case.transaction_metadata or {}
        def _yes(k: str) -> bool:
            return str(meta.get(k, "")).lower() in {"yes", "true", "1"}
        password_reset = _yes("password_reset_before")
        device_changed = _yes("new_device")
        phone_changed = _yes("mobile_number_changed")
        sim_swap = _yes("sim_swap_suspected")
        ato_signals = sum([password_reset, device_changed, phone_changed, sim_swap])
        ato_risk = ("CRITICAL" if ato_signals >= 3 else "HIGH" if ato_signals >= 2
                    else "MEDIUM" if ato_signals == 1 else "LOW")
        return (
            "ACCOUNT TAKEOVER PATTERN REPORT\n"
            f"  Password Reset Before : {'Yes' if password_reset else 'No'}\n"
            f"  New Device Detected   : {'Yes' if device_changed else 'No'}\n"
            f"  Mobile Number Changed : {'Yes' if phone_changed else 'No'}\n"
            f"  SIM Swap Suspected    : {'Yes' if sim_swap else 'No'}\n"
            f"  ATO Signal Count      : {ato_signals}\n"
            f"  Account Takeover Risk : {ato_risk}\n"
            f"  Assessment            : {'CRITICAL account takeover — multiple compromise indicators.' if ato_risk == 'CRITICAL' else 'High ATO risk — multiple signals detected.' if ato_risk == 'HIGH' else 'Moderate ATO signal detected.' if ato_risk == 'MEDIUM' else 'No account takeover pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_account_takeover_pattern failed: {exc}")
        return f"ACCOUNT TAKEOVER PATTERN REPORT\n  Error: {exc}\n  Account Takeover Risk: LOW"
    finally:
        db.close()


@tool
def analyze_mule_account_indicators(case_id: str) -> str:
    """Detect mule account behavior — rapid pass-through of funds indicating money laundering."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from datetime import datetime, timezone, timedelta
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "MULE ACCOUNT INDICATORS\n  Mule Account Suspected: No"
        customer_id = case.customer_id or ""
        now = datetime.now(timezone.utc)
        txns_24h = db.query(Transaction).filter(
            Transaction.customer_id == customer_id.upper(),
            Transaction.transaction_date >= now - timedelta(hours=24),
            Transaction.status == "Success",
        ).all()
        total_24h = len(txns_24h)
        high_velocity = total_24h >= 8
        txns_2h = [t for t in txns_24h if t.transaction_date and (now - (t.transaction_date.replace(tzinfo=timezone.utc) if t.transaction_date.tzinfo is None else t.transaction_date)).total_seconds() <= 7200]
        unique_merchants_2h = len({t.merchant_name for t in txns_2h if t.merchant_name})
        scatter_pattern = unique_merchants_2h >= 5
        mule_suspected = high_velocity or scatter_pattern
        return (
            "MULE ACCOUNT INDICATORS REPORT\n"
            f"  Transactions (24h)    : {total_24h}\n"
            f"  Unique Merchants (2h) : {unique_merchants_2h}\n"
            f"  High Velocity (24h)   : {'Yes' if high_velocity else 'No'}\n"
            f"  Scatter Pattern (2h)  : {'Yes' if scatter_pattern else 'No'}\n"
            f"  Mule Account Suspected: {'Yes' if mule_suspected else 'No'}\n"
            f"  Assessment            : {'Mule account behavior detected — rapid fund pass-through pattern.' if mule_suspected else 'No mule account pattern detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"analyze_mule_account_indicators failed: {exc}")
        return f"MULE ACCOUNT INDICATORS REPORT\n  Error: {exc}\n  Mule Account Suspected: No"
    finally:
        db.close()


@tool
def detect_historical_case_similarity(case_id: str) -> str:
    """Compare current dispute against historical database to identify known fraud patterns."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory
    from datetime import datetime, timezone, timedelta
    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return "HISTORICAL CASE SIMILARITY\n  Pattern Risk: LOW"
        merchant = (case.merchant or "").lower()
        dispute_category = case.dispute_category or ""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=90)
        hist_all = db.query(DisputeHistory).filter(DisputeHistory.created_at >= cutoff).all()
        similar_cases = len(hist_all)
        same_merchant = sum(1 for h in hist_all if merchant and merchant in (h.merchant_id or "").lower())
        fraud_cases = sum(1 for h in hist_all if h.fraud_claim)
        cat_matches = sum(1 for h in hist_all if (h.dispute_category or "") == dispute_category)
        similarity_score = min(1.0, (same_merchant * 0.4 + fraud_cases * 0.4 + cat_matches * 0.2) / max(similar_cases, 10))
        pattern_risk = "HIGH" if similarity_score > 0.6 else "MEDIUM" if similarity_score > 0.3 else "LOW"
        return (
            "HISTORICAL CASE SIMILARITY REPORT\n"
            f"  Similar Cases Found     : {similar_cases}\n"
            f"  Same Merchant Disputes  : {same_merchant}\n"
            f"  Fraud-Flagged Cases     : {fraud_cases}\n"
            f"  Similarity Score        : {similarity_score:.2f}\n"
            f"  Pattern Risk            : {pattern_risk}\n"
            f"  Assessment              : {'High similarity to known fraud patterns — strong historical match.' if pattern_risk == 'HIGH' else 'Moderate pattern similarity detected.' if pattern_risk == 'MEDIUM' else 'No significant pattern match in historical cases.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_historical_case_similarity failed: {exc}")
        return f"HISTORICAL CASE SIMILARITY REPORT\n  Error: {exc}\n  Pattern Risk: LOW"
    finally:
        db.close()


# ── Tool: Linked Fraud Network Detection ─────────────────────────────────────

@tool
def detect_linked_fraud_network(case_id: str) -> str:
    """Detect fraud network connections by checking whether the same phone, email,
    device ID, or beneficiary (merchant) appears across multiple customers' disputes.
    Identifies organised fraud rings where different victims were targeted by the same actor."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "LINKED FRAUD NETWORK\n  Error: Case not found\n  Fraud Network Detected: No"

        phone    = (case.phone or "").strip()
        email    = (case.email or "").strip().lower()
        merchant = (case.merchant or "").strip().lower()
        meta     = case.transaction_metadata or {}
        device_id = (meta.get("device_id") or "").strip()

        linked_cases: set[str] = set()

        # Check same phone across other disputes
        if phone:
            matches = db.query(DisputeCase).filter(
                DisputeCase.phone == phone,
                DisputeCase.case_id != case_id.upper(),
            ).all()
            for m in matches:
                linked_cases.add(m.case_id)

        # Check same email
        if email:
            matches = db.query(DisputeCase).filter(
                DisputeCase.email.ilike(email),
                DisputeCase.case_id != case_id.upper(),
            ).all()
            for m in matches:
                linked_cases.add(m.case_id)

        # Check same beneficiary (merchant) across other customers
        if merchant:
            matches = db.query(DisputeCase).filter(
                DisputeCase.merchant.ilike(f"%{merchant}%"),
                DisputeCase.customer_id != case.customer_id,
            ).all()
            for m in matches:
                linked_cases.add(m.case_id)
            # Also check dispute history
            hist = db.query(DisputeHistory).filter(
                DisputeHistory.customer_id != case.customer_id,
            ).all()
            for h in hist:
                if merchant in (h.merchant_id or "").lower():
                    linked_cases.add(h.case_id)

        count = len(linked_cases)
        network_detected = count >= 3

        risk = "HIGH" if count >= 5 else "MEDIUM" if count >= 3 else "LOW"

        return (
            "LINKED FRAUD NETWORK\n"
            f"  Case ID              : {case_id}\n"
            f"  Linked Cases Found   : {count}\n"
            f"  Fraud Network Detected: {'Yes — ALERT' if network_detected else 'No'}\n"
            f"  Network Risk         : {risk}\n"
            f"  Assessment           : {'Shared contact or beneficiary pattern across {count} other disputes — possible organised fraud ring.' if network_detected else 'No significant network connections detected.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_linked_fraud_network failed: {exc}")
        return f"LINKED FRAUD NETWORK\n  Error: {exc}\n  Fraud Network Detected: No"
    finally:
        db.close()


# ── Tool: Rapid Case Creation Pattern ────────────────────────────────────────

@tool
def detect_rapid_case_creation(case_id: str) -> str:
    """Detect customers who file disputes at an unusually high rate — a strong indicator
    of friendly fraud (fabricated disputes to extract refunds) or systematic abuse."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "RAPID CASE CREATION\n  Error: Case not found\n  Repeat Dispute Pattern: No"

        customer_id = case.customer_id.upper()
        now = datetime.now(timezone.utc)

        # Count disputes in last 30 days (live + history)
        cutoff_30 = now - timedelta(days=30)
        cutoff_90 = now - timedelta(days=90)

        def _count(days: int) -> int:
            cutoff = now - timedelta(days=days)
            live = db.query(DisputeCase).filter(
                DisputeCase.customer_id == customer_id,
                DisputeCase.case_id != case_id.upper(),
                DisputeCase.created_at >= cutoff,
            ).count()
            hist = db.query(DisputeHistory).filter(
                DisputeHistory.customer_id == customer_id,
                DisputeHistory.created_at >= cutoff,
            ).count()
            return live + hist

        count_30d = _count(30)
        count_90d = _count(90)

        # Threshold: 3+ in 30 days OR 5+ in 90 days
        rapid_pattern = count_30d >= 3 or count_90d >= 5

        if count_30d >= 3:
            trigger = f"{count_30d} disputes in last 30 days (threshold: 3)"
        elif count_90d >= 5:
            trigger = f"{count_90d} disputes in last 90 days (threshold: 5)"
        else:
            trigger = "Within normal dispute frequency"

        return (
            "RAPID CASE CREATION REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Disputes (Last 30d)  : {count_30d}\n"
            f"  Disputes (Last 90d)  : {count_90d}\n"
            f"  Repeat Dispute Pattern: {'Yes — ALERT' if rapid_pattern else 'No'}\n"
            f"  Trigger              : {trigger}\n"
            f"  Assessment           : {'Unusually high dispute frequency — review for friendly fraud or abuse pattern.' if rapid_pattern else 'Dispute frequency within normal range.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_rapid_case_creation failed: {exc}")
        return f"RAPID CASE CREATION\n  Error: {exc}\n  Repeat Dispute Pattern: No"
    finally:
        db.close()


# ── Bank-Verified Account Intelligence Tools ──────────────────────────────────

# Weighted ATO event types — higher weight = stronger signal when appearing before a transaction
_ATO_EVENT_WEIGHTS: dict[str, float] = {
    "SIM_SWAP_DETECTED":     3.0,   # telecom-level takeover — very strong
    "ACCOUNT_LOCKED":        2.5,   # brute-force or automated attack
    "FRAUD_ALERT":           2.5,   # bank's own system flagged suspicious activity
    "MOBILE_NUMBER_CHANGED": 2.0,   # intercept OTP setup
    "DEVICE_TRUST_CHANGED":  1.5,   # bank downgraded device trust
    "DEVICE_REGISTERED":     1.5,   # new device added before transaction
    "BENEFICIARY_ADDED":     1.5,   # new payee added before large transfer
    "DEVICE_REMOVED":        1.0,   # old device removed (often precedes new one)
    "PASSWORD_RESET":        1.0,   # common alone; strong in combination
    "EMAIL_CHANGED":         1.0,   # contact change that could intercept alerts
}
_ATO_EVENT_TYPES = set(_ATO_EVENT_WEIGHTS.keys())


def _parse_txn_datetime(transaction_date: str, transaction_time: str):
    from datetime import datetime, timezone
    try:
        s = f"{transaction_date} {transaction_time}".strip()
        fmt = "%Y-%m-%d %H:%M" if len(transaction_time.split(":")) == 2 else "%Y-%m-%d %H:%M:%S"
        return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


@tool
def verify_account_takeover_sequence(case_id: str) -> str:
    """Detect ATO by reading bank-observed security events from account_events table.
    Looks for PASSWORD_RESET, DEVICE_REGISTERED, MOBILE_NUMBER_CHANGED, BENEFICIARY_ADDED,
    SIM_SWAP_DETECTED events within 30 days before the disputed transaction.
    Uses ONLY bank system records — not customer-reported form answers."""
    from database.database import SessionLocal
    from database.models import DisputeCase
    from services.account_intelligence_service import get_ato_events

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "ATO SEQUENCE ANALYSIS\n  Error: Case not found\n  ATO Risk: LOW\n  Verification Mode: NO_DATA"

        txn_dt = _parse_txn_datetime(case.transaction_date or "", case.transaction_time or "")
        events = get_ato_events(case.customer_id, txn_dt, db, 30)

        if not events:
            return (
                "ATO SEQUENCE ANALYSIS\n"
                f"  Customer ID      : {case.customer_id}\n"
                "  ATO Risk         : LOW\n"
                "  ATO Events Found : 0\n"
                "  Verification Mode: BANK_VERIFIED\n"
                "  Assessment       : No bank-observed ATO events in the 30-day window."
            )

        # Weighted scoring — not just count, but severity of events
        verified = [e for e in events if e["event_type"] in _ATO_EVENT_TYPES]
        verified_types = list({e["event_type"] for e in verified})
        weight_total = sum(_ATO_EVENT_WEIGHTS.get(et, 1.0) for et in verified_types)

        # Sorted by weight descending for display
        verified_types_sorted = sorted(verified_types, key=lambda t: _ATO_EVENT_WEIGHTS.get(t, 1.0), reverse=True)

        # Risk based on weighted score (not raw count)
        if weight_total >= 5.0:   ato_risk = "CRITICAL"
        elif weight_total >= 3.0: ato_risk = "HIGH"
        elif weight_total >= 1.0: ato_risk = "MEDIUM"
        else:                     ato_risk = "LOW"

        events_str = ", ".join(verified_types_sorted) if verified_types_sorted else "None"
        return (
            "ATO SEQUENCE ANALYSIS\n"
            f"  Customer ID      : {case.customer_id}\n"
            f"  ATO Risk         : {ato_risk}\n"
            f"  Verified Events  : {len(verified_types)} ({events_str})\n"
            f"  ATO Weight Score : {round(weight_total, 1)}\n"
            f"  Verification Mode: BANK_VERIFIED\n"
            f"  Assessment       : {'ATO sequence detected in bank records — weighted score ' + str(round(weight_total,1)) + '.' if weight_total > 0 else 'No ATO sequence in bank records.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"verify_account_takeover_sequence failed: {exc}")
        return f"ATO SEQUENCE ANALYSIS\n  Error: {exc}\n  ATO Risk: LOW\n  Verification Mode: CUSTOMER_REPORTED"
    finally:
        db.close()


@tool
def verify_device_intelligence(case_id: str) -> str:
    """Verify device trust status from customer_devices registry.
    Determines if the transaction device is known, trusted, recently registered, or completely new.
    Uses bank device records — not customer-reported claims."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction
    from services.account_intelligence_service import get_device_status

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "DEVICE INTELLIGENCE\n  Error: Case not found\n  Fraud Signal: LOW\n  Verification Mode: NO_DATA"

        # Get device_id from actual transaction record
        txn = db.query(Transaction).filter(Transaction.transaction_id == case.transaction_id).first()
        device_id = (txn.device_id or "") if txn else ""
        txn_dt = _parse_txn_datetime(case.transaction_date or "", case.transaction_time or "")

        status = get_device_status(case.customer_id, device_id, txn_dt, db)

        # Check if large transfer
        all_txns = db.query(Transaction).filter(Transaction.customer_id == case.customer_id.upper()).all()
        amounts = [t.amount for t in all_txns if t.amount and t.transaction_id != case.transaction_id]
        avg = sum(amounts) / len(amounts) if amounts else 0.0
        large_transfer = float(case.amount or 0) > avg * 2 and avg > 0

        ds = status["device_status"]
        if ds == "NEW_DEVICE" and large_transfer:
            fraud_signal = "CRITICAL"
        elif ds == "NEW_DEVICE":
            fraud_signal = "HIGH"
        elif ds == "RECENTLY_REGISTERED":
            fraud_signal = "MEDIUM"
        else:
            fraud_signal = "LOW"

        return (
            "DEVICE INTELLIGENCE\n"
            f"  Customer ID      : {case.customer_id}\n"
            f"  Device ID        : {device_id or 'Not available'}\n"
            f"  Device Status    : {ds}\n"
            f"  Trusted          : {'Yes' if status['trusted'] else 'No'}\n"
            f"  Device Age (hrs) : {status['device_age_hours'] or 'N/A'}\n"
            f"  Large Transfer   : {'Yes' if large_transfer else 'No'}\n"
            f"  Fraud Signal     : {fraud_signal}\n"
            f"  Verification Mode: BANK_VERIFIED\n"
            f"  Assessment       : {ds} device {'with large transfer — critical ATO signal.' if fraud_signal == 'CRITICAL' else '— elevated fraud risk.' if fraud_signal in ('HIGH','MEDIUM') else '— normal pattern.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"verify_device_intelligence failed: {exc}")
        return f"DEVICE INTELLIGENCE\n  Error: {exc}\n  Fraud Signal: LOW\n  Verification Mode: CUSTOMER_REPORTED"
    finally:
        db.close()


@tool
def verify_mobile_change(case_id: str) -> str:
    """Check bank account_events for MOBILE_NUMBER_CHANGED within 7 days before disputed transaction.
    Mobile number changes before transactions are a strong ATO signal — fraudster intercepts OTPs."""
    from database.database import SessionLocal
    from database.models import DisputeCase, AccountEvent
    from datetime import timedelta, timezone

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "MOBILE CHANGE VERIFICATION\n  Error: Case not found\n  Mobile Change Detected: No\n  Verification Mode: NO_DATA"

        txn_dt = _parse_txn_datetime(case.transaction_date or "", case.transaction_time or "")
        cutoff = txn_dt - timedelta(days=7)

        event = (
            db.query(AccountEvent)
            .filter(
                AccountEvent.customer_id == case.customer_id.upper(),
                AccountEvent.event_type == "MOBILE_NUMBER_CHANGED",
                AccountEvent.event_timestamp >= cutoff,
                AccountEvent.event_timestamp <= txn_dt,
            )
            .order_by(AccountEvent.event_timestamp.desc())
            .first()
        )

        if not event:
            return (
                "MOBILE CHANGE VERIFICATION\n"
                f"  Customer ID             : {case.customer_id}\n"
                "  Mobile Change Detected  : No\n"
                "  Verification Mode       : BANK_VERIFIED\n"
                "  Assessment              : No mobile number change in bank records within 7 days."
            )

        et = event.event_timestamp
        if et.tzinfo is None: et = et.replace(tzinfo=timezone.utc)
        hours_before = round((txn_dt - et).total_seconds() / 3600, 1)

        return (
            "MOBILE CHANGE VERIFICATION\n"
            f"  Customer ID             : {case.customer_id}\n"
            "  Mobile Change Detected  : Yes — ALERT\n"
            f"  Hours Before Txn        : {hours_before}\n"
            "  Verification Mode       : BANK_VERIFIED\n"
            f"  Assessment              : MOBILE_NUMBER_CHANGED recorded {hours_before}h before disputed transaction — OTP interception risk."
        )
    except Exception as exc:
        agent_logger.warning(f"verify_mobile_change failed: {exc}")
        return f"MOBILE CHANGE VERIFICATION\n  Error: {exc}\n  Mobile Change Detected: No\n  Verification Mode: CUSTOMER_REPORTED"
    finally:
        db.close()


@tool
def verify_new_beneficiary_activity(case_id: str) -> str:
    """Check beneficiaries table to determine if the disputed merchant/payee is a known
    beneficiary or was recently added. New beneficiaries for large amounts = strong fraud signal."""
    from database.database import SessionLocal
    from database.models import DisputeCase, AccountEvent
    from services.account_intelligence_service import get_beneficiary_status

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "BENEFICIARY INTELLIGENCE\n  Error: Case not found\n  New Beneficiary: No\n  Verification Mode: NO_DATA"

        txn_dt = _parse_txn_datetime(case.transaction_date or "", case.transaction_time or "")
        bstatus = get_beneficiary_status(case.customer_id, case.merchant or "", txn_dt, db)

        # Also check if BENEFICIARY_ADDED event exists for this merchant
        bene_event = None
        if not bstatus["known_beneficiary"]:
            from datetime import timedelta
            bene_event = (
                db.query(AccountEvent)
                .filter(
                    AccountEvent.customer_id == case.customer_id.upper(),
                    AccountEvent.event_type == "BENEFICIARY_ADDED",
                    AccountEvent.event_timestamp >= txn_dt - timedelta(days=7),
                    AccountEvent.event_timestamp <= txn_dt,
                )
                .first()
            )

        new_beneficiary = not bstatus["known_beneficiary"]
        age_note = ""
        if bene_event:
            from datetime import timezone as _tz
            et = bene_event.event_timestamp
            if et.tzinfo is None: et = et.replace(tzinfo=_tz.utc)
            hrs = round((txn_dt - et).total_seconds() / 3600, 1)
            age_note = f"  Beneficiary Added   : {hrs}h before transaction (bank event)\n"

        fraud_signal = "HIGH" if new_beneficiary else "LOW"

        return (
            "BENEFICIARY INTELLIGENCE\n"
            f"  Customer ID         : {case.customer_id}\n"
            f"  Merchant / Payee    : {case.merchant}\n"
            f"  Known Beneficiary   : {'Yes' if not new_beneficiary else 'No'}\n"
            f"  New Beneficiary     : {'Yes — ALERT' if new_beneficiary else 'No'}\n"
            + age_note +
            f"  Fraud Signal        : {fraud_signal}\n"
            f"  Verification Mode   : BANK_VERIFIED\n"
            f"  Assessment          : {'First-time payee — not in customer beneficiary registry.' if new_beneficiary else 'Known beneficiary with prior transaction history.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"verify_new_beneficiary_activity failed: {exc}")
        return f"BENEFICIARY INTELLIGENCE\n  Error: {exc}\n  New Beneficiary: No\n  Verification Mode: CUSTOMER_REPORTED"
    finally:
        db.close()


@tool
def validate_customer_security_claims(case_id: str) -> str:
    """Cross-reference customer-reported security claims against bank account_events.
    Determines VERIFIED, PARTIALLY_VERIFIED, or UNVERIFIED status.
    Does NOT affect fraud_probability — affects confidence and reasoning quality only."""
    from database.database import SessionLocal
    from database.models import DisputeCase, AccountEvent, CustomerDevice
    from datetime import timedelta

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id.upper()).first()
        if not case:
            return "CLAIM VALIDATION\n  Error: Case not found\n  Identity Verification Status: UNVERIFIED\n  Verification Mode: NO_DATA"

        meta = case.transaction_metadata or {}
        txn_dt = _parse_txn_datetime(case.transaction_date or "", case.transaction_time or "")
        cutoff = txn_dt - timedelta(days=30)

        events = db.query(AccountEvent).filter(
            AccountEvent.customer_id == case.customer_id.upper(),
            AccountEvent.event_timestamp >= cutoff,
        ).all()
        event_types = {e.event_type for e in events}

        def _claim_val(claim_key: str, bank_event: str) -> str:
            claimed = str(meta.get(claim_key, "")).strip().lower() in {"yes", "true", "1", "True"}
            if not claimed:
                return "NOT_CLAIMED"
            return "VERIFIED" if bank_event in event_types else "UNVERIFIED"

        validations = {
            "password_reset":    _claim_val("password_reset_before", "PASSWORD_RESET"),
            "sim_swap":          _claim_val("sim_swap_suspected", "SIM_SWAP_DETECTED"),
            "mobile_change":     _claim_val("mobile_number_changed", "MOBILE_NUMBER_CHANGED"),
        }

        # Device claim
        from database.models import Transaction as _Txn
        txn = db.query(_Txn).filter(_Txn.transaction_id == case.transaction_id).first()
        device_id = (txn.device_id or "") if txn else ""
        if device_id:
            dev = db.query(CustomerDevice).filter(
                CustomerDevice.customer_id == case.customer_id.upper(),
                CustomerDevice.device_id == device_id,
            ).first()
            validations["new_device"] = "VERIFIED" if not dev or not dev.trusted else "UNVERIFIED"
        else:
            validations["new_device"] = "NOT_CLAIMED"

        active = {k: v for k, v in validations.items() if v != "NOT_CLAIMED"}
        verified_count = sum(1 for v in active.values() if v == "VERIFIED")
        total_claimed = len(active)

        if total_claimed == 0:
            id_status = "NO_CLAIMS"
        elif verified_count == total_claimed:
            id_status = "VERIFIED"
        elif verified_count >= total_claimed / 2:
            id_status = "PARTIALLY_VERIFIED"
        else:
            id_status = "UNVERIFIED"

        val_str = " | ".join(f"{k}={v}" for k, v in validations.items())

        return (
            "CLAIM VALIDATION\n"
            f"  Customer ID                 : {case.customer_id}\n"
            f"  Claims Checked              : {total_claimed}\n"
            f"  Claims Verified             : {verified_count}\n"
            f"  Claim Validations           : {val_str}\n"
            f"  Identity Verification Status: {id_status}\n"
            f"  Verification Mode           : BANK_VERIFIED\n"
            f"  Assessment                  : {verified_count}/{total_claimed} customer claims corroborated by bank records."
        )
    except Exception as exc:
        agent_logger.warning(f"validate_customer_security_claims failed: {exc}")
        return f"CLAIM VALIDATION\n  Error: {exc}\n  Identity Verification Status: UNVERIFIED\n  Verification Mode: CUSTOMER_REPORTED"
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
    # Card POS — advanced intelligence
    "detect_merchant_compromise_pattern":  detect_merchant_compromise_pattern,
    "analyze_first_time_merchant":         analyze_first_time_merchant,
    "evaluate_merchant_resolution_history": evaluate_merchant_resolution_history,
    "detect_card_testing_pattern":         detect_card_testing_pattern,
    "analyze_multi_merchant_burst":        analyze_multi_merchant_burst,
    "evaluate_mcc_risk":                   evaluate_mcc_risk,
    "analyze_decline_success_pattern":     analyze_decline_success_pattern,
    "check_refund_reversal_absence":       check_refund_reversal_absence,
    # UPI intelligence
    "analyze_new_beneficiary_risk":           analyze_new_beneficiary_risk,
    "detect_upi_collect_request_fraud":       detect_upi_collect_request_fraud,
    "analyze_beneficiary_velocity":           analyze_beneficiary_velocity,
    "evaluate_upi_handle_reputation":         evaluate_upi_handle_reputation,
    "analyze_dormant_beneficiary_risk":       analyze_dormant_beneficiary_risk,
    # Internet / Mobile Banking intelligence
    "detect_impossible_login_travel":             detect_impossible_login_travel,
    "analyze_device_change_large_transfer":       analyze_device_change_large_transfer,
    "detect_password_reset_transaction_pattern":  detect_password_reset_transaction_pattern,
    "analyze_mobile_number_change_risk":          analyze_mobile_number_change_risk,
    # ATM intelligence
    "analyze_consecutive_atm_withdrawals":  analyze_consecutive_atm_withdrawals,
    "analyze_foreign_atm_usage":            analyze_foreign_atm_usage,
    "detect_sim_swap_atm_pattern":          detect_sim_swap_atm_pattern,
    # Universal
    "evaluate_historical_fraud_victim_score": evaluate_historical_fraud_victim_score,
    "detect_account_takeover_pattern":        detect_account_takeover_pattern,
    "analyze_mule_account_indicators":        analyze_mule_account_indicators,
    "detect_historical_case_similarity":      detect_historical_case_similarity,
    "detect_linked_fraud_network":            detect_linked_fraud_network,
    "detect_rapid_case_creation":             detect_rapid_case_creation,
    # Bank-verified account intelligence
    "verify_account_takeover_sequence":       verify_account_takeover_sequence,
    "verify_device_intelligence":             verify_device_intelligence,
    "verify_mobile_change":                   verify_mobile_change,
    "verify_new_beneficiary_activity":        verify_new_beneficiary_activity,
    "validate_customer_security_claims":      validate_customer_security_claims,
}
