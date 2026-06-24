"""
Shared routing constants used by queue_assignment_service and orchestration_agent.
Single source of truth for which risk tags trigger compliance routing.
"""

# AML / regulatory signals — shared base used by both queue routing and WOA.
# DUPLICATE_PAYMENT and RECURRING_DISPUTE are chargeback patterns, not AML.
COMPLIANCE_TAGS: frozenset = frozenset({
    "VELOCITY_BREACH",       # Multiple transactions in short window — AML signal
    "SUSPICIOUS_BEHAVIOR",   # Unusual pattern detected
    "MERCHANT_BLACKLISTED",  # Known scam merchant — regulatory escalation needed
    "DEVICE_MISMATCH",       # Transaction from unrecognized device — AML/KYC review
    "OTP_COMPROMISED",          # Customer shared OTP — social engineering, compliance must review
})

# FRIENDLY_FRAUD_RISK warrants a compliance review step in the investigation
# workflow (WOA adds it) but does NOT route the case to the compliance analyst
# queue — it stays in CHARGEBACK_TEAM / MERCHANT_DISPUTES.
COMPLIANCE_AGENT_TAGS: frozenset = COMPLIANCE_TAGS | frozenset({"FRIENDLY_FRAUD_RISK"})

