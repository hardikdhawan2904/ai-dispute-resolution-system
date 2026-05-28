"""
Internal ↔ customer status mapping.

Also provides ops-display label normalization — reduces AI visibility
by converting technical labels to banking operations language.
"""

# Internal status → ops-display label (already human-friendly)
OPS_STATUS_LABELS = {
    "Dispute Raised":      "Dispute Raised",
    "Under Investigation": "Under Investigation",
    "Pending Documents":   "Pending Documents",
    "Escalated":           "Escalated",
    "Resolved":            "Resolved",
    "Rejected":            "Rejected",
    "Closed":              "Closed",
}

# Internal field → ops display label (reduces AI jargon)
OPS_FIELD_LABELS = {
    "dispute_category":       "Transaction Category",
    "fraud_suspicion":        "Fraud Indicator",
    "customer_intent_summary":"Investigation Summary",
    "confidence_score":       "Review Confidence",
    "structured_reasoning":   "Investigation Notes",
    "risk_tags":              "Risk Indicators",
    "priority":               "Priority Level",
}

# Customer-facing status map
CUSTOMER_STATUS_MAP = {
    "Dispute Raised":      "Dispute Submitted",
    "Under Investigation": "Under Review",
    "Pending Documents":   "Documents Requested",
    "Escalated":           "Investigation In Progress",
    "Resolved":            "Resolved",
    "Rejected":            "Resolved",
    "Closed":              "Resolved",
}

ESTIMATED_RESOLUTION = {
    "Dispute Raised":      "Within 7 business days",
    "Under Investigation": "Within 5 business days",
    "Pending Documents":   "Within 5 business days of document receipt",
    "Escalated":           "Within 3 business days",
    "Resolved":            "Resolved",
    "Rejected":            "Resolved",
    "Closed":              "Closed",
}


def get_ops_display(case: dict) -> dict:
    """Add ops-friendly display labels to a case dict."""
    return {
        **case,
        "_display_labels": OPS_FIELD_LABELS,
    }
