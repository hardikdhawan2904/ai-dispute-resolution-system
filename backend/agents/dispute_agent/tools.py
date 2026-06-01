"""
ARIA dispute agent tools — all pure, deterministic @tool functions.
No LLM call lives inside any tool; the agent LLM calls these autonomously.

Usage anywhere in the codebase:
    from agents.dispute_agent.tools import validate_dispute_input
    result = validate_dispute_input.invoke({"customer_id": "C123"})

    from agents.dispute_agent.tools import TOOLS
    llm.bind_tools(TOOLS)
"""
import json
from typing import List

from langchain_core.tools import tool

from utils.helpers import determine_priority, generate_case_id
from utils.logger import agent_logger


@tool
def validate_dispute_input(customer_id: str, existing_case_id: str = "") -> str:
    """Validate the dispute submission and return a case ID.
    Pass existing_case_id if one already exists; leave empty to auto-generate.
    Always call this first before any other tool."""
    case_id = existing_case_id.strip() if existing_case_id.strip() else generate_case_id()
    agent_logger.info("Case validated", extra={"case_id": case_id, "customer_id": customer_id})
    return case_id


@tool
def build_evidence_summary(metadata_json: str) -> str:
    """Build a structured fraud-indicator checklist from transaction metadata.
    Pass the transaction_metadata field as a JSON string.
    Call this after validate_dispute_input; use the result in your analysis."""
    try:
        meta = json.loads(metadata_json)
    except Exception:
        meta = {}

    def yn(val) -> str:
        if val is True:  return "Yes"
        if val is False: return "No"
        return str(val) if val else "Not provided"

    return (
        f"  OTP Received (for this txn)  : {yn(meta.get('otp_received'))}\n"
        f"  Card / Account Blocked       : {yn(meta.get('card_blocked'))}\n"
        f"  Bank Already Contacted       : {yn(meta.get('bank_contacted'))}\n"
        f"  Transaction Location         : {meta.get('transaction_location') or 'Not provided'}\n"
        f"  OTP Shared with 3rd Party    : {yn(meta.get('otp_shared'))}\n"
        f"  Bank Impersonation Call      : {yn(meta.get('bank_impersonation'))}\n"
        f"  Remote Access App Installed  : {yn(meta.get('remote_access'))}\n"
        f"  Phishing Link Clicked        : {yn(meta.get('phishing_link'))}\n"
        f"  SIM Swap Suspected           : {yn(meta.get('sim_swap_suspected'))}\n"
        f"  Device Lost / Stolen         : {yn(meta.get('device_lost'))}\n"
        f"  Card Lost / Stolen           : {yn(meta.get('card_lost'))}\n"
        f"  Unknown Beneficiary Added    : {yn(meta.get('unknown_beneficiary'))}\n"
        f"  UPI Collect Fraud            : {yn(meta.get('upi_collect_fraud'))}\n"
        f"  Steps Already Taken          : {meta.get('fraud_additional_details') or 'None stated'}\n"
    )


@tool
def clamp_score(score: float) -> float:
    """Clamp a confidence score to the valid [0.0, 1.0] range.
    Call this with the confidence_score from your analysis before finalizing."""
    return max(0.0, min(1.0, score))


@tool
def calculate_priority(amount: float, fraud_suspicion: bool, risk_tags: List[str]) -> str:
    """Determine case priority from amount and fraud indicators.
    Returns one of: CRITICAL, HIGH, MEDIUM, LOW.
    Call this if you are unsure about priority or want to validate your assessment."""
    return determine_priority(amount, fraud_suspicion, risk_tags)


# ── All tools — the LLM agent calls all of these autonomously ────────────────
TOOLS = [validate_dispute_input, build_evidence_summary, calculate_priority, clamp_score]
