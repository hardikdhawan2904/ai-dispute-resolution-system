"""
Shared routing constants used by queue_assignment_service and orchestration_agent.
Single source of truth for which risk tags trigger escalation.
"""

# High-risk tags that trigger case escalation (senior analyst / manual review).
# COMPLIANCE_AGENT has been removed — these tags now trigger escalation only,
# not a separate compliance workflow step.
ESCALATION_TAGS: frozenset = frozenset({
    "VELOCITY_BREACH",       # Multiple transactions in short window — AML signal
    "SUSPICIOUS_BEHAVIOR",   # Unusual pattern detected
    "MERCHANT_BLACKLISTED",  # Known scam merchant — regulatory escalation needed
    "DEVICE_MISMATCH",       # Transaction from unrecognized device — AML/KYC review
    "OTP_COMPROMISED",       # Customer shared OTP — social engineering escalation
    "FRIENDLY_FRAUD_RISK",   # Repeat dispute pattern — senior analyst needed
})

# Backwards-compat alias — used by orchestration_agent tools import
COMPLIANCE_TAGS: frozenset = ESCALATION_TAGS
COMPLIANCE_AGENT_TAGS: frozenset = ESCALATION_TAGS

