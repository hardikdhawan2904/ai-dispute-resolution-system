"""
Investigation Intelligence Agent tools — 5 tools that query real data.

Each tool:
  - is decorated with @tool (docstring becomes LLM JSON schema)
  - opens its own DB session and closes it on exit
  - returns a human-readable string the LLM cites in its reasoning

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
    """Query the bank's dispute_cases table for this customer's complete dispute history.
    Returns total disputes, fraud-flag count, last dispute recency, and a risk level.
    Use this to assess whether the customer is a first-time disputer, a repeat claimant,
    or a high-risk fraud-flag customer."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        query = db.query(DisputeCase).filter(DisputeCase.customer_id == customer_id)
        # Exclude the active case and any cases submitted after it (not yet history)
        exclude_id = _active_case_id.get()
        if exclude_id:
            query = query.filter(DisputeCase.case_id != exclude_id)
            current_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if current_case and current_case.created_at:
                query = query.filter(DisputeCase.created_at < current_case.created_at)
        cases = query.all()

        if not cases:
            return (
                "CUSTOMER HISTORY\n"
                f"  Customer ID          : {customer_id}\n"
                "  Previous Disputes    : 0\n"
                "  Fraud Claims         : 0\n"
                "  Last Dispute         : Never\n"
                "  Risk Level           : LOW\n"
                "  Assessment           : First-time disputer — no prior history."
            )

        total       = len(cases)
        fraud_count = sum(1 for c in cases if c.fraud_suspicion)
        cats        = [c.dispute_category for c in cases if c.dispute_category]
        top_cats    = Counter(cats).most_common(3)
        fraud_rate  = fraud_count / total

        # Recency — find most recent case excluding current
        sorted_cases = sorted(cases, key=lambda c: c.created_at or datetime.min, reverse=True)
        last_case    = sorted_cases[0]
        if last_case.created_at:
            last_dt = last_case.created_at
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            days_ago = (datetime.now(timezone.utc) - last_dt).days
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

        return (
            "CUSTOMER HISTORY\n"
            f"  Customer ID          : {customer_id}\n"
            f"  Previous Disputes    : {total}\n"
            f"  Fraud Claims         : {fraud_count} ({fraud_rate:.0%} of cases)\n"
            f"  Last Dispute         : {days_ago} days ago\n"
            f"  Top Categories       : {', '.join(f'{c}({n})' for c, n in top_cats) or 'None'}\n"
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
    """Query the bank's dispute_cases table for all complaints filed against this merchant.
    Also checks the merchant name against known scam and blacklist patterns.
    Returns total complaints, fraud rate, top dispute categories, and merchant risk level.
    Use this for Merchant Dispute, Refund Not Received, Product Not Received, Subscription Abuse,
    and any case where fraud_suspicion is true."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        query = (
            db.query(DisputeCase)
            .filter(DisputeCase.merchant.ilike(f"%{merchant_name[:30]}%"))
        )
        # Exclude the active case and any submitted after it (not yet historical)
        exclude_id = _active_case_id.get()
        if exclude_id:
            query = query.filter(DisputeCase.case_id != exclude_id)
            current_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if current_case and current_case.created_at:
                query = query.filter(DisputeCase.created_at < current_case.created_at)
        cases = query.all()

        merchant_lower  = merchant_name.lower()
        blacklisted     = any(p in merchant_lower for p in _BLACKLIST_PATTERNS)

        if not cases:
            note = " WARNING: matches known scam name patterns." if blacklisted else ""
            return (
                "MERCHANT RISK\n"
                f"  Merchant             : {merchant_name}\n"
                f"  Prior Complaints     : 0{note}\n"
                f"  Fraud Rate           : 0%\n"
                f"  Blacklist Match      : {'YES' if blacklisted else 'No'}\n"
                f"  Merchant Risk        : {'HIGH (blacklist)' if blacklisted else 'UNKNOWN'}\n"
                "  Assessment           : No complaints on record."
            )

        total       = len(cases)
        fraud_count = sum(1 for c in cases if c.fraud_suspicion)
        cats        = [c.dispute_category for c in cases if c.dispute_category]
        top_cats    = Counter(cats).most_common(3)
        fraud_rate  = fraud_count / total

        if blacklisted or fraud_rate > 0.6 or total > 20:
            risk = "CRITICAL"
        elif fraud_rate > 0.3 or total > 8:
            risk = "HIGH"
        elif fraud_rate > 0.1 or total > 3:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return (
            "MERCHANT RISK\n"
            f"  Merchant             : {merchant_name}\n"
            f"  Prior Complaints     : {total}\n"
            f"  Fraud Rate           : {fraud_rate:.0%}\n"
            f"  Top Categories       : {', '.join(f'{c}({n})' for c, n in top_cats)}\n"
            f"  Blacklist Match      : {'YES — extreme caution' if blacklisted else 'No'}\n"
            f"  Merchant Risk        : {risk}\n"
            f"  Assessment           : {'Escalate immediately — pattern of fraud complaints.' if risk == 'CRITICAL' else 'High complaint volume — investigate merchant practices.' if risk == 'HIGH' else 'Some complaints — standard merchant investigation.' if risk == 'MEDIUM' else 'Clean record — focus on transaction specifics.'}"
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
    """Search dispute_cases for duplicate or near-duplicate disputes already in the system.
    Performs two checks:
      1. Exact match on transaction_id (same transaction already disputed)
      2. Same customer + merchant + amount filed within the last 72 hours
    Returns whether a duplicate was found and the related case ID if applicable.
    Use this for Duplicate Transaction disputes and Unauthorized Transaction disputes."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        found: List[str] = []
        related_ids: List[str] = []

        # Check 1 — exact transaction_id match
        if transaction_id:
            for c in db.query(DisputeCase).filter(
                DisputeCase.transaction_id == transaction_id
            ).all():
                found.append(
                    f"Case {c.case_id} — same transaction_id, "
                    f"status: {c.status}, filed: {str(c.created_at)[:10]}"
                )
                related_ids.append(c.case_id)

        # Check 2 — same customer + merchant + amount within 72 h
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        for c in db.query(DisputeCase).filter(
            DisputeCase.customer_id == customer_id,
            DisputeCase.merchant.ilike(f"%{merchant[:20]}%"),
            DisputeCase.amount == amount,
            DisputeCase.created_at >= cutoff,
        ).all():
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
    """Search dispute_cases for historical cases with the same dispute_category.
    Optionally filters by merchant name for merchant-specific patterns.
    Returns total similar cases, resolution outcomes (resolved in favour / rejected),
    and the overall resolution rate. Use this to gauge precedent and likely outcome."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        query = db.query(DisputeCase).filter(
            DisputeCase.dispute_category == dispute_category
        )
        if merchant:
            query = query.filter(DisputeCase.merchant.ilike(f"%{merchant[:20]}%"))
        # Exclude the active case and any submitted after it
        exclude_id = _active_case_id.get()
        if exclude_id:
            query = query.filter(DisputeCase.case_id != exclude_id)
            current_case = db.query(DisputeCase).filter(DisputeCase.case_id == exclude_id).first()
            if current_case and current_case.created_at:
                query = query.filter(DisputeCase.created_at < current_case.created_at)

        cases = query.all()

        if not cases:
            return (
                "RELATED CASES\n"
                f"  Dispute Category     : {dispute_category}\n"
                "  Similar Cases        : 0\n"
                "  Assessment           : No historical precedent found for this category."
            )

        total         = len(cases)
        resolved      = sum(1 for c in cases if c.status == "Resolved")
        rejected      = sum(1 for c in cases if c.status == "Rejected")
        closed        = sum(1 for c in cases if c.status == "Closed")
        still_open    = total - resolved - rejected - closed
        resolution_rate = resolved / total if total > 0 else 0

        avg_conf = sum(c.confidence_score for c in cases if c.confidence_score) / total

        return (
            "RELATED CASES\n"
            f"  Dispute Category     : {dispute_category}\n"
            f"  Similar Cases        : {total}\n"
            f"  Resolved in Favour   : {resolved}\n"
            f"  Rejected             : {rejected}\n"
            f"  Closed               : {closed}\n"
            f"  Still Open           : {still_open}\n"
            f"  Resolution Rate      : {resolution_rate:.0%}\n"
            f"  Avg Confidence Score : {avg_conf:.2f}\n"
            f"  Assessment           : {'Strong precedent for customer — high resolution rate.' if resolution_rate > 0.7 else 'Moderate precedent — outcome depends on evidence quality.' if resolution_rate > 0.4 else 'Low resolution rate — thorough evidence required.'}"
        )
    except Exception as exc:
        agent_logger.warning(f"lookup_related_cases failed: {exc}")
        return f"RELATED CASES\n  Error: Tool execution failed — {exc}"
    finally:
        db.close()


# ── Tool 5 — Document recommendation ─────────────────────────────────────────

_DOCUMENT_MAP: dict = {
    "Unauthorized Transaction": [
        "Bank statement (last 3 months)",
        "SMS / email transaction alert screenshot",
        "OTP receipt (if applicable)",
        "Police FIR or written complaint (if filed)",
        "Account activity report",
    ],
    "Duplicate Transaction": [
        "Bank statement showing both charges",
        "Transaction receipt or confirmation",
        "Merchant order confirmation",
        "Payment gateway reference numbers",
    ],
    "Refund Not Received": [
        "Original payment receipt",
        "Refund confirmation from merchant",
        "Bank statement (last 30 days)",
        "Merchant communication (email / chat screenshot)",
        "Order cancellation confirmation",
    ],
    "Product Not Received": [
        "Order confirmation or invoice",
        "Payment receipt",
        "Merchant communication",
        "Delivery tracking information",
        "Screenshot of order status",
    ],
    "Subscription Abuse": [
        "Subscription terms and conditions",
        "Cancellation confirmation (if obtained)",
        "Bank statement showing recurring charges",
        "Merchant communication",
        "Screenshot of account cancellation",
    ],
    "ATM Cash Issue": [
        "ATM transaction receipt",
        "Bank statement showing debit",
        "ATM reference number",
        "CCTV request form (if applicable)",
        "Written complaint to branch (if filed)",
    ],
    "Merchant Dispute": [
        "Original invoice or receipt",
        "Merchant communication (email / chat / SMS)",
        "Photos of product or service (if relevant)",
        "Payment confirmation",
        "Menu or price list at time of transaction",
    ],
    "Friendly Fraud": [
        "Original purchase receipt",
        "Proof of transaction authorisation",
        "Device or IP access logs",
        "Any communication with customer",
        "Merchant delivery confirmation",
    ],
    "Other": [
        "Bank statement (last 3 months)",
        "Any supporting documentation",
        "Customer statutory declaration",
    ],
}

_FRAUD_EXTRA = [
    "Police FIR or written complaint",
    "OTP transaction logs",
]

_HIGH_VALUE_EXTRA = [
    "KYC verification documents",
    "Source of funds declaration",
]


@tool
def recommend_documents(
    dispute_category: str,
    fraud_suspicion: bool,
    risk_tags: str,
) -> str:
    """Recommend the required supporting documents based on dispute category,
    fraud suspicion flag, and active risk tags.
    Always call this for every dispute — analyst queue cannot proceed without a document checklist.
    Pass risk_tags as a comma-separated string."""
    base = list(_DOCUMENT_MAP.get(dispute_category, _DOCUMENT_MAP["Other"]))

    tags = [t.strip().upper() for t in risk_tags.split(",") if t.strip()]

    if fraud_suspicion:
        for doc in _FRAUD_EXTRA:
            if doc not in base:
                base.append(doc)

    if "HIGH_VALUE_TRANSACTION" in tags:
        for doc in _HIGH_VALUE_EXTRA:
            if doc not in base:
                base.append(doc)

    if "OTP_VERIFIED" in tags and "OTP transaction logs" not in base:
        base.append("OTP transaction logs")

    if "INTERNATIONAL_TRANSACTION" in tags:
        base.append("Passport or travel document (proof of location at transaction time)")

    doc_list = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(base))
    return (
        f"REQUIRED DOCUMENTS — {dispute_category}\n"
        f"{doc_list}\n"
        f"  Total Required       : {len(base)}"
    )


# ── Registry ──────────────────────────────────────────────────────────────────
# graph.py and pipeline.py resolve callables by reading agent_tools from agent.yaml
# and looking each name up here. Add a new tool here + in agent.yaml — nowhere else.

TOOL_REGISTRY: dict = {
    "lookup_customer_history":    lookup_customer_history,
    "check_merchant_risk":        check_merchant_risk,
    "find_duplicate_transaction": find_duplicate_transaction,
    "lookup_related_cases":       lookup_related_cases,
    "recommend_documents":        recommend_documents,
}
