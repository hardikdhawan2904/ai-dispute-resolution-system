"""
Deterministic BFSI document requirements — single source of truth.
No LLM needed: requirements are rule-based per dispute category.

Used by:
  - workflows/dispute_workflow.py  →  document sufficiency gate (before agents run)
  - agents/investigation_agent     →  stamp required_documents server-side
  - api/routes/disputes.py         →  /document-requirements endpoint (frontend Step 4)
"""
from __future__ import annotations

from typing import List, Tuple

# ── Bank-obtainable documents — bank retrieves these internally ───────────────
# The customer is NOT responsible for submitting these. Mirrors the frontend
# BANK_OBTAINABLE set in internal-review/[caseId]/page.tsx — keep in sync.

BANK_OBTAINABLE: frozenset[str] = frozenset({
    "Merchant order confirmation",
    "Payment gateway reference numbers",
    "CCTV request form (if applicable)",
    "Device or IP access logs",
    "OTP transaction logs",
    "Account activity report",
    "ATM reference number",
    "Merchant delivery confirmation",
    "Proof of transaction authorisation",
    "Any communication with customer",
    "Menu or price list at time of transaction",
})


# ── Per-category required document lists ──────────────────────────────────────

_DOCUMENT_MAP: dict[str, List[str]] = {
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

# Extra documents for fraud cases
_FRAUD_EXTRA: List[str] = [
    "Police FIR or written complaint",
    "OTP transaction logs",
]

# Extra documents for high-value cases (> ₹50,000)
_HIGH_VALUE_EXTRA: List[str] = [
    "Source of funds declaration",
]

# Documents the bank or merchant obtains internally — NOT requested from the customer.
# These appear in the internal required_documents list for analyst reference
# but are filtered out before showing to the customer on the tracking page.
_BANK_OBTAINABLE: set[str] = {
    "Merchant order confirmation",
    "Payment gateway reference numbers",
    "CCTV request form (if applicable)",
    "Device or IP access logs",
    "OTP transaction logs",
    "Account activity report",
    "ATM reference number",
    "Merchant delivery confirmation",
    "Proof of transaction authorisation",
    "Any communication with customer",
    "Menu or price list at time of transaction",
    "KYC verification documents",  # bank already holds customer KYC on file
}


def get_customer_required_documents(
    category: str,
    fraud_selected: bool = False,
    amount: float = 0.0,
    risk_tags: List[str] | None = None,
    transaction_type: str = "",
) -> List[str]:
    """Return only the documents the customer can actually upload.
    Filters out bank/merchant-obtainable documents from the full list."""
    full = get_required_documents(category, fraud_selected, amount, risk_tags, transaction_type)
    return [d for d in full if d not in _BANK_OBTAINABLE]


# Minimum documents required to start AI analysis (by category).
# Based on RBI dispute adjudication requirements:
#   - Fraud / Unauthorized: FIR or bank statement mandatory
#   - ATM: receipt or reference number mandatory
#   - Refund / Product: order receipt or merchant communication mandatory
_MIN_DOCS: dict[str, int] = {
    "Unauthorized Transaction": 2,   # Bank statement + one fraud evidence doc
    "Duplicate Transaction":    2,   # Both charge receipts or statement
    "Refund Not Received":      2,   # Payment proof + refund request evidence
    "Product Not Received":     2,   # Order confirmation + delivery failure proof
    "Subscription Abuse":       1,   # Bank statement showing recurring charge
    "ATM Cash Issue":           1,   # ATM receipt or reference number
    "Merchant Dispute":         1,   # Original invoice or receipt
    "Friendly Fraud":           2,   # Purchase proof + authorisation evidence
    "Other":                    1,   # At least one supporting document
}

# Keyword → category mapping for pre-classification at intake
_REASON_KEYWORDS: dict[str, List[str]] = {
    "Unauthorized Transaction": [
        "unauthorized", "fraud", "stolen", "hacked", "sim swap",
        "not me", "didn't do", "did not do", "account takeover", "unknown transaction",
    ],
    "Duplicate Transaction": [
        "duplicate", "charged twice", "double charge", "debited twice",
    ],
    "Refund Not Received": [
        "refund", "return", "cancelled", "cancellation", "money back",
    ],
    "Product Not Received": [
        "not received", "not delivered", "delivery failed", "item not",
    ],
    "Subscription Abuse": [
        "subscription", "recurring", "auto-debit", "auto debit", "unsubscribed",
    ],
    "ATM Cash Issue": [
        "atm", "cash not dispensed", "cash withdrawal", "cash issue",
    ],
    "Merchant Dispute": [
        "merchant", "overcharged", "wrong amount", "service issue", "incorrect charge",
    ],
}


def infer_category(dispute_reason: str) -> str:
    """Map free-text dispute_reason to a dispute category."""
    lower = dispute_reason.lower()
    for category, keywords in _REASON_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "Other"


def get_required_documents(
    category: str,
    fraud_selected: bool = False,
    amount: float = 0.0,
    risk_tags: List[str] | None = None,
    transaction_type: str = "",
) -> List[str]:
    """Return the full required document list for this dispute."""
    base = list(_DOCUMENT_MAP.get(category, _DOCUMENT_MAP["Other"]))

    if fraud_selected:
        for doc in _FRAUD_EXTRA:
            if doc not in base:
                base.append(doc)

    if amount > 50_000:
        for doc in _HIGH_VALUE_EXTRA:
            if doc not in base:
                base.append(doc)

    if risk_tags:
        tags_upper = [t.upper() for t in risk_tags]
        if "OTP_VERIFIED" in tags_upper and "OTP transaction logs" not in base:
            base.append("OTP transaction logs")
        # Only require passport when transaction type is genuinely International,
        # not just because Agent 1 added the risk tag on a domestic transaction
        if (
            "INTERNATIONAL_TRANSACTION" in tags_upper
            and transaction_type.strip().lower() == "international"
        ):
            base.append("Passport or travel document (proof of location at transaction time)")

    return base


def minimum_document_count(
    category: str,
    fraud_selected: bool = False,
    amount: float = 0.0,
) -> int:
    """Minimum number of evidence files required to start analysis."""
    base_min = _MIN_DOCS.get(category, 1)
    if fraud_selected or amount > 50_000:
        return max(base_min, 2)
    return base_min


def resolve_investigation_status(case, case_id: str) -> str:
    """
    Determine the correct case status based on customer-required docs vs uploaded files.

    Returns "Under Investigation" when all customer-side documents have been received,
    "Pending Documents" when the customer still has items to submit,
    or the existing status unchanged for terminal cases.

    This is the single source of truth for the Pending Documents ↔ Under Investigation
    transition and must be used by every re-analysis path.
    """
    if case.status in ("Resolved", "Rejected", "Closed", "Escalated"):
        return case.status

    import pathlib
    customer_docs = get_customer_required_documents(
        category        = case.dispute_category or "Other",
        fraud_selected  = case.fraud_selected or False,
        amount          = float(case.amount or 0),
        risk_tags       = case.risk_tags or [],
        transaction_type = case.transaction_type or "",
    )

    upload_dir   = pathlib.Path("uploads") / str(case_id)
    upload_count = len([f for f in upload_dir.iterdir() if f.is_file()]) if upload_dir.exists() else 0

    if not customer_docs:
        # No customer-side docs required — move to Under Investigation once any analysis ran
        return "Under Investigation" if (case.evidence_match is not None or upload_count > 0) else case.status

    return "Under Investigation" if upload_count >= len(customer_docs) else "Pending Documents"


def check_documents_sufficient(
    category: str,
    fraud_selected: bool,
    amount: float,
    document_count: int,
) -> Tuple[bool, List[str]]:
    """
    Check whether submitted documents meet the minimum threshold.
    Returns (is_sufficient, full_required_list).
    """
    required  = get_required_documents(category, fraud_selected, amount)
    min_count = minimum_document_count(category, fraud_selected, amount)
    return document_count >= min_count, required
