"""
Fraud Reasoning Agent tools — 3 tools that query database tables.
"""
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
        velocity_breach = txn_count_24h >= 3

        status = "SUSPICIOUS" if (is_off_hours or velocity_breach) else "NORMAL"
        reasons = []
        if is_off_hours:
            reasons.append("Transaction processed during off-hours (11 PM - 5 AM).")
        if velocity_breach:
            reasons.append(f"High velocity breach: {txn_count_24h} transactions executed in the last 24 hours.")

        assessment = " | ".join(reasons) if reasons else "Transaction patterns within normal velocity and timing limits."

        return (
            "TRANSACTION ANOMALY DETECTION REPORT\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Status               : {status}\n"
            f"  Transaction Date/Time: {transaction_date} {transaction_time}\n"
            f"  Off-Hours Flag       : {'Yes' if is_off_hours else 'No'}\n"
            f"  24h Transaction Count: {txn_count_24h}\n"
            f"  Velocity Breach      : {'Yes — ALERT' if velocity_breach else 'No'}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"detect_transaction_anomalies failed: {exc}")
        return f"TRANSACTION ANOMALY DETECTION REPORT\n  Error: Tool execution failed — {exc}\n  Status: SUSPICIOUS"
    finally:
        db.close()


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
        if not location:
            return (
                "GEOGRAPHIC VELOCITY REPORT\n"
                f"  Customer ID      : {customer_id}\n"
                "  Geovelocity Risk : LOW\n"
                "  Assessment       : No transaction location metadata available."
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
            if diff < 4.0 and t.location and t.location.strip().lower() != location.strip().lower():
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


from collections import Counter


# ── Tool 4 — KYC Profile verification ─────────────────────────────────────────

@tool
def verify_kyc_match(customer_id: str, name: str, email: str, phone: str) -> str:
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

        if all_match:
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


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "detect_transaction_anomalies": detect_transaction_anomalies,
    "evaluate_location_velocity":    evaluate_location_velocity,
    "analyze_spending_behavior":     analyze_spending_behavior,
    "verify_kyc_match":             verify_kyc_match,
    "evaluate_device_fingerprint":  evaluate_device_fingerprint,
    "analyze_behavioral_patterns":  analyze_behavioral_patterns,
}
