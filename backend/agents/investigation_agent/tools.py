"""
Investigation Intelligence Agent tools — 5 tools that query real data.

Each tool:
  - is decorated with @tool (docstring becomes LLM JSON schema)
  - opens its own DB session and closes it on exit
  - returns a human-readable string the LLM cites in its reasoning

Data sources (queried in priority order):
  1. dispute_history   — 526+ pre-seeded resolved historical disputes
  2. dispute_cases     — live disputes submitted through the system
  3. merchant_profiles — merchant risk profile and complaint stats
  4. transactions      — 11 000+ real customer transaction records

To add a new tool:
  1. Define it here with @tool and register it in TOOL_REGISTRY.
  2. Add its name to agent_tools in agent.yaml.
  That's it — graph.py and pipeline.py pick it up automatically.
"""
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from typing import List

from langchain_core.tools import tool

from utils.logger import agent_logger

# Injected server-side before graph invocation — never passed by the LLM
_active_case_id: ContextVar[str] = ContextVar("active_case_id", default="")


# ── Tool 1 — Customer history ─────────────────────────────────────────────────

@tool
def lookup_customer_history(customer_id: str) -> str:
    """Query the bank's dispute history and live dispute cases for this customer's
    complete dispute record. Returns total disputes, fraud-flag count, last dispute
    recency, top categories, and a risk level. Covers both pre-existing history and
    any live cases. Use this to assess first-time vs repeat vs high-risk customers."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory

    db = SessionLocal()
    try:
        exclude_id   = _active_case_id.get()
        cutoff_dt    = None

        if exclude_id:
            current_case = db.query(DisputeCase).filter(
                DisputeCase.case_id == exclude_id
            ).first()
            if current_case and current_case.created_at:
                cutoff_dt = current_case.created_at

        # ── historical disputes (dispute_history) ────────────────────────────
        hist_q = db.query(DisputeHistory).filter(
            DisputeHistory.customer_id == customer_id
        )
        if cutoff_dt:
            hist_q = hist_q.filter(DisputeHistory.created_at < cutoff_dt)
        hist_cases = hist_q.all()

        # ── live disputes (dispute_cases) ────────────────────────────────────
        live_q = db.query(DisputeCase).filter(
            DisputeCase.customer_id == customer_id
        )
        if exclude_id:
            live_q = live_q.filter(DisputeCase.case_id != exclude_id)
        if cutoff_dt:
            live_q = live_q.filter(DisputeCase.created_at < cutoff_dt)
        live_cases = live_q.all()

        # ── aggregate ────────────────────────────────────────────────────────
        hist_total  = len(hist_cases)
        live_total  = len(live_cases)
        total       = hist_total + live_total

        if total == 0:
            return (
                "CUSTOMER HISTORY\n"
                f"  Customer ID          : {customer_id}\n"
                "  Previous Disputes    : 0\n"
                "  Fraud Claims         : 0\n"
                "  Last Dispute         : Never\n"
                "  Risk Level           : LOW\n"
                "  Assessment           : First-time disputer — no prior history."
            )

        hist_fraud = sum(1 for c in hist_cases if c.fraud_claim)
        live_fraud = sum(1 for c in live_cases if c.fraud_suspicion)
        fraud_count = hist_fraud + live_fraud
        fraud_rate  = fraud_count / total

        # top categories from both sources
        cats = (
            [c.dispute_category for c in hist_cases if c.dispute_category]
            + [c.dispute_category for c in live_cases if c.dispute_category]
        )
        top_cats = Counter(cats).most_common(3)

        # resolved-in-favour stats from history
        cust_favour  = sum(1 for c in hist_cases if c.resolved_in_favor_of == "customer")
        merch_favour = sum(1 for c in hist_cases if c.resolved_in_favor_of == "merchant")
        avg_days     = (
            sum(c.resolution_days for c in hist_cases if c.resolution_days)
            / max(1, sum(1 for c in hist_cases if c.resolution_days))
        )

        # recency — most recent date across both sources
        all_dates = []
        for c in hist_cases:
            if c.created_at:
                dt = c.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                all_dates.append(dt)
        for c in live_cases:
            if c.created_at:
                dt = c.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                all_dates.append(dt)
        if all_dates:
            days_ago = (datetime.now(timezone.utc) - max(all_dates)).days
        else:
            days_ago = -1

        if fraud_rate > 0.5 and total >= 3:
            risk = "HIGH"
            assessment = "Majority of disputes were fraud-flagged — verify this claim carefully."
        elif total >= 5:
            risk = "MEDIUM"
            assessment = "Frequent disputer — review for friendly fraud risk."
        elif fraud_count > 0:
            risk = "MEDIUM"
            assessment = "Has prior fraud claims — cross-check with current dispute type."
        else:
            risk = "LOW"
            assessment = "Normal dispute pattern."

        favour_line = (
            f"Resolved for Customer: {cust_favour}, for Merchant: {merch_favour}"
            if hist_total > 0 else "No resolved history available"
        )

        return (
            "CUSTOMER HISTORY\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Previous Disputes    : {total} ({hist_total} historical + {live_total} live)\n"
            f"  Fraud Claims         : {fraud_count} ({fraud_rate:.0%} of cases)\n"
            f"  Last Dispute         : {days_ago} days ago\n"
            f"  Top Categories       : {', '.join(f'{c}({n})' for c, n in top_cats) or 'None'}\n"
            f"  Resolution History   : {favour_line}\n"
            f"  Avg Resolution Days  : {avg_days:.0f}\n"
            f"  Risk Level           : {risk}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"lookup_customer_history failed: {exc}")
        return f"CUSTOMER HISTORY\n  Error: Tool execution failed — {exc}\n  Risk Level: UNKNOWN"
    finally:
        db.close()


# ── Tool 2 — Merchant risk ────────────────────────────────────────────────────

_BLACKLIST_PATTERNS = {
    "flash", "lucky", "prize", "win", "reward", "lottery",
    "crypto", "bitcoin", "forex", "investment returns",
    "unlimited", "scheme", "jackpot", "doubl", "ponzi",
}


@tool
def check_merchant_risk(merchant_name: str) -> str:
    """Query merchant_profiles for the merchant's pre-computed risk profile, then
    cross-check with dispute_history and live dispute_cases for any complaints.
    Returns prior complaints, fraud rate, resolution outcomes, risk level, and
    blacklist status. Use for Merchant Dispute, Refund Not Received, Product Not
    Received, Subscription Abuse, and any case where fraud_suspicion is true."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory, MerchantProfile

    db = SessionLocal()
    try:
        exclude_id = _active_case_id.get()
        cutoff_dt  = None
        if exclude_id:
            current_case = db.query(DisputeCase).filter(
                DisputeCase.case_id == exclude_id
            ).first()
            if current_case and current_case.created_at:
                cutoff_dt = current_case.created_at

        merchant_lower = merchant_name.lower()
        keyword_blacklisted = any(p in merchant_lower for p in _BLACKLIST_PATTERNS)

        # ── look up merchant profile ──────────────────────────────────────────
        profile = db.query(MerchantProfile).filter(
            MerchantProfile.merchant_name.ilike(f"%{merchant_name[:30]}%")
        ).first()

        # ── historical complaints ─────────────────────────────────────────────
        if profile:
            hist_q = db.query(DisputeHistory).filter(
                DisputeHistory.merchant_id == profile.merchant_id
            )
        else:
            hist_q = db.query(DisputeHistory).filter(DisputeHistory.merchant_id == None)  # noqa
        if cutoff_dt:
            hist_q = hist_q.filter(DisputeHistory.created_at < cutoff_dt)
        hist_cases = hist_q.all()

        # ── live complaints ───────────────────────────────────────────────────
        live_q = db.query(DisputeCase).filter(
            DisputeCase.merchant.ilike(f"%{merchant_name[:30]}%")
        )
        if exclude_id:
            live_q = live_q.filter(DisputeCase.case_id != exclude_id)
        if cutoff_dt:
            live_q = live_q.filter(DisputeCase.created_at < cutoff_dt)
        live_cases = live_q.all()

        # ── aggregate ─────────────────────────────────────────────────────────
        hist_total  = len(hist_cases)
        live_total  = len(live_cases)
        total       = hist_total + live_total

        hist_fraud  = sum(1 for c in hist_cases if c.fraud_claim)
        live_fraud  = sum(1 for c in live_cases if c.fraud_suspicion)
        fraud_count = hist_fraud + live_fraud

        db_blacklisted = profile.blacklisted if profile else False
        blacklisted    = db_blacklisted or keyword_blacklisted

        if total == 0:
            note       = " WARNING: matches known scam name patterns." if blacklisted else ""
            risk_label = "HIGH (blacklist)" if blacklisted else "LOW"
            profile_risk = profile.risk_level if profile else "LOW"
            return (
                "MERCHANT RISK\n"
                f"  Merchant             : {merchant_name}\n"
                f"  Profile Risk Level   : {profile_risk}\n"
                f"  Prior Complaints     : 0{note}\n"
                f"  Fraud Rate           : 0%\n"
                f"  Blacklist Match      : {'YES' if blacklisted else 'No'}\n"
                f"  Merchant Risk        : {risk_label}\n"
                "  Assessment           : No complaints on record — clean merchant history."
            )

        fraud_rate = fraud_count / total
        cats       = (
            [c.dispute_category for c in hist_cases if c.dispute_category]
            + [c.dispute_category for c in live_cases if c.dispute_category]
        )
        top_cats  = Counter(cats).most_common(3)
        cust_fav  = sum(1 for c in hist_cases if c.resolved_in_favor_of == "customer")
        merch_fav = sum(1 for c in hist_cases if c.resolved_in_favor_of == "merchant")

        if blacklisted or fraud_rate > 0.6 or total > 20:
            risk = "CRITICAL"
        elif fraud_rate > 0.3 or total > 8:
            risk = "HIGH"
        elif fraud_rate > 0.1 or total > 3:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        if profile:
            profile.risk_level = risk
            db.commit()

        if risk == "CRITICAL":
            assessment = "Escalate immediately — pattern of fraud complaints."
        elif risk == "HIGH":
            assessment = "High complaint volume — investigate merchant practices."
        elif risk == "MEDIUM":
            assessment = "Some complaints — standard merchant investigation."
        else:
            assessment = "Clean record — focus on transaction specifics."

        return (
            "MERCHANT RISK\n"
            f"  Merchant             : {merchant_name}\n"
            f"  Total Complaints     : {total} ({hist_total} historical + {live_total} live)\n"
            f"  Fraud Rate           : {fraud_rate:.0%}\n"
            f"  Top Categories       : {', '.join(f'{c}({n})' for c, n in top_cats)}\n"
            f"  Resolved for Customer: {cust_fav} / for Merchant: {merch_fav}\n"
            f"  Blacklist Match      : {'YES — extreme caution' if blacklisted else 'No'}\n"
            f"  Merchant Risk        : {risk}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"check_merchant_risk failed: {exc}")
        return f"MERCHANT RISK\n  Error: Tool execution failed — {exc}\n  Merchant Risk: UNKNOWN"
    finally:
        db.close()


# ── Tool 3 — Duplicate detection ──────────────────────────────────────────────

@tool
def find_duplicate_transaction(
    transaction_id: str,
    customer_id: str,
    amount: float,
    merchant: str,
) -> str:
    """Search for duplicate or near-duplicate transactions in the transactions table
    and in existing dispute_cases. Performs three checks:
      1. Exact match on transaction_id in the transactions table
      2. Exact match on transaction_id in existing dispute_cases
      3. Same customer + merchant + amount within the last 72 hours in dispute_cases
    Returns whether a duplicate was found and related case/transaction IDs.
    Use this for Duplicate Transaction disputes and Unauthorized Transaction disputes."""
    from database.database import SessionLocal
    from database.models import DisputeCase, Transaction

    db = SessionLocal()
    try:
        found:       List[str] = []
        related_ids: List[str] = []
        exclude_id = _active_case_id.get()

        # Check 1 — exact transaction_id in dispute_cases OTHER than the current case
        if transaction_id:
            q = db.query(DisputeCase).filter(
                DisputeCase.transaction_id == transaction_id
            )
            if exclude_id:
                q = q.filter(DisputeCase.case_id != exclude_id)
            for c in q.all():
                found.append(
                    f"Case {c.case_id} — same transaction_id already disputed, "
                    f"status: {c.status}, filed: {str(c.created_at)[:10]}"
                )
                related_ids.append(c.case_id)

        # Check 3 — same customer + merchant + amount within 72 h in dispute_cases
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        q2 = db.query(DisputeCase).filter(
            DisputeCase.customer_id == customer_id,
            DisputeCase.merchant.ilike(f"%{merchant[:20]}%"),
            DisputeCase.amount == amount,
            DisputeCase.created_at >= cutoff,
        )
        if exclude_id:
            q2 = q2.filter(DisputeCase.case_id != exclude_id)
        for c in q2.all():
            entry = (
                f"Case {c.case_id} — same customer+merchant+amount "
                f"within 72h, status: {c.status}"
            )
            if entry not in found:
                found.append(entry)
                related_ids.append(c.case_id)

        if not found:
            return (
                "DUPLICATE CHECK\n"
                "  Duplicate Found      : No\n"
                "  Related Case ID      : None\n"
                "  Assessment           : This is a unique dispute submission."
            )

        return (
            "DUPLICATE CHECK\n"
            f"  Duplicate Found      : Yes — {len(found)} match(es)\n"
            f"  Related Case ID      : {related_ids[0]}\n"
            "  Matches:\n"
            + "\n".join(f"    • {f}" for f in found)
            + "\n  Assessment           : Link to existing case and verify if re-submission or separate charge."
        )
    except Exception as exc:
        agent_logger.warning(f"find_duplicate_transaction failed: {exc}")
        return f"DUPLICATE CHECK\n  Error: Tool execution failed — {exc}\n  Duplicate Found: UNKNOWN"
    finally:
        db.close()


# ── Tool 4 — Related cases ────────────────────────────────────────────────────

@tool
def lookup_related_cases(dispute_category: str, merchant: str = "") -> str:
    """Search dispute_history (historical resolved disputes) and live dispute_cases
    for cases with the same dispute_category. Optionally filters by merchant name.
    Returns similar case count, resolution outcomes, and the overall resolution rate.
    Use this to gauge precedent and likely outcome for this type of dispute."""
    from database.database import SessionLocal
    from database.models import DisputeCase, DisputeHistory

    db = SessionLocal()
    try:
        exclude_id = _active_case_id.get()
        cutoff_dt  = None
        if exclude_id:
            current_case = db.query(DisputeCase).filter(
                DisputeCase.case_id == exclude_id
            ).first()
            if current_case and current_case.created_at:
                cutoff_dt = current_case.created_at

        # ── historical cases ──────────────────────────────────────────────────
        hist_q = db.query(DisputeHistory).filter(
            DisputeHistory.dispute_category == dispute_category
        )
        if cutoff_dt:
            hist_q = hist_q.filter(DisputeHistory.created_at < cutoff_dt)
        hist_cases = hist_q.all()

        # ── live cases ────────────────────────────────────────────────────────
        live_q = db.query(DisputeCase).filter(
            DisputeCase.dispute_category == dispute_category
        )
        if merchant:
            live_q = live_q.filter(DisputeCase.merchant.ilike(f"%{merchant[:20]}%"))
        if exclude_id:
            live_q = live_q.filter(DisputeCase.case_id != exclude_id)
        if cutoff_dt:
            live_q = live_q.filter(DisputeCase.created_at < cutoff_dt)
        live_cases = live_q.all()

        hist_total = len(hist_cases)
        live_total = len(live_cases)
        total      = hist_total + live_total

        if total == 0:
            return (
                "RELATED CASES\n"
                f"  Dispute Category     : {dispute_category}\n"
                "  Similar Cases        : 0\n"
                "  Assessment           : No historical precedent found for this category."
            )

        # resolution breakdown from historical data (most reliable)
        hist_resolved = sum(1 for c in hist_cases if c.status == "Resolved")
        hist_rejected = sum(1 for c in hist_cases if c.status == "Rejected")
        hist_closed   = sum(1 for c in hist_cases if c.status == "Closed")
        hist_cust_fav = sum(1 for c in hist_cases if c.resolved_in_favor_of == "customer")
        hist_merch_fav= sum(1 for c in hist_cases if c.resolved_in_favor_of == "merchant")
        avg_res_days  = (
            sum(c.resolution_days for c in hist_cases if c.resolution_days)
            / max(1, sum(1 for c in hist_cases if c.resolution_days))
        )

        # live case breakdown
        live_resolved = sum(1 for c in live_cases if c.status == "Resolved")
        live_rejected = sum(1 for c in live_cases if c.status == "Rejected")
        live_open     = live_total - live_resolved - live_rejected

        # overall resolution rate = customer-favour resolutions / all resolved
        total_resolved = hist_resolved + live_resolved
        resolution_rate = total_resolved / total if total > 0 else 0

        if resolution_rate > 0.7:
            assessment = "Strong precedent for customer — high resolution rate."
        elif resolution_rate > 0.4:
            assessment = "Moderate precedent — outcome depends on evidence quality."
        else:
            assessment = "Low resolution rate — thorough evidence required."

        return (
            "RELATED CASES\n"
            f"  Dispute Category     : {dispute_category}\n"
            f"  Similar Cases        : {total} ({hist_total} historical + {live_total} live)\n"
            f"  Resolved in Favour   : {hist_cust_fav} customer / {hist_merch_fav} merchant (historical)\n"
            f"  Rejected             : {hist_rejected + live_rejected}\n"
            f"  Closed               : {hist_closed}\n"
            f"  Live Open            : {live_open}\n"
            f"  Resolution Rate      : {resolution_rate:.0%}\n"
            f"  Avg Resolution Days  : {avg_res_days:.0f}\n"
            f"  Assessment           : {assessment}"
        )
    except Exception as exc:
        agent_logger.warning(f"lookup_related_cases failed: {exc}")
        return f"RELATED CASES\n  Error: Tool execution failed — {exc}"
    finally:
        db.close()


# ── Registry ──────────────────────────────────────────────────────────────────
# Document requirements are computed by services/document_rules.py (deterministic,
# no LLM needed) and stamped server-side in the investigation finalize_node.

TOOL_REGISTRY: dict = {
    "lookup_customer_history":    lookup_customer_history,
    "check_merchant_risk":        check_merchant_risk,
    "find_duplicate_transaction": find_duplicate_transaction,
    "lookup_related_cases":       lookup_related_cases,
}
