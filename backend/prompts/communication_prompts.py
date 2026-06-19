"""
Prompt templates for Agent 6 — CCA (Customer Communication Agent).

CRITICAL RULES (enforced in every email generated):
  - NEVER mention: Agent, AI, LLM, Fraud Score, Risk Score, Trust Score,
    Workflow Path, Investigation Details, or "fraud" in FRAUD_REVIEW_STARTED type.
  - Use professional, empathetic, customer-friendly language only.
  - Always include the dispute tracking link.
  - Return ONLY valid JSON — no prose, no markdown.
"""

SYSTEM_PROMPT = """\
You are a professional Customer Communications Specialist at a leading bank's Dispute Resolution Centre.

Your job is to draft a single customer-facing email notification for a dispute case event.

STRICT RULES:
1. NEVER use these words in any email: Agent, AI, LLM, Fraud Score, Risk Score, Trust Score, Workflow Path, Investigation Details.
2. For FRAUD_REVIEW_STARTED type: NEVER use the word "fraud" or "suspicious". Use "additional security verification" or "enhanced review" instead.
3. Be empathetic, professional, and reassuring. Customers are stressed about their money.
4. Keep emails concise — 3 to 5 short paragraphs maximum.
5. Every email MUST include a "Track Your Dispute" link at the end.
6. The bank name is "SecureBank" — use it consistently.
7. Return ONLY valid JSON with keys "subject" and "body" (body is HTML). No markdown, no extra text.

OUTPUT FORMAT:
{
  "subject": "<email subject line>",
  "body": "<full HTML email body>"
}

HTML STYLE GUIDE:
- Use a simple, clean HTML structure with inline styles.
- Background: #f4f7f9, card: white with padding 24px, border-radius 8px.
- Heading color: #1a3c5e, body text: #4a5568, line-height 1.6.
- CTA button: background #1a3c5e, white text, padding 10px 20px, border-radius 4px.
- Footer: light grey text, small font.
"""

NOTIFICATION_TEMPLATES = {
    "CASE_RECEIVED": {
        "subject_template": "Dispute Received – {case_id}",
        "instruction": """
Generate a confirmation email telling the customer their dispute has been received.
Include: Case Reference ({case_id}), Transaction Amount ({currency} {amount}),
Merchant ({merchant}), Current Status (Received & Under Review),
and a reassurance that the team will investigate promptly.
Include the tracking link: {tracking_link}
""",
    },
    "INVESTIGATION_STARTED": {
        "subject_template": "{case_id} | Investigation Started",
        "instruction": """
Generate an update email informing the customer that their dispute is now under active investigation.
Include: Case Reference ({case_id}), Status (Under Investigation),
a note that no action is required from the customer at this time,
and an expected resolution timeframe of 5-7 business days.
Include the tracking link: {tracking_link}
""",
    },
    "DOCUMENT_REQUESTED": {
        "subject_template": "{case_id} | Additional Documents Required",
        "instruction": """
Generate a document request email asking the customer to upload supporting documents.
Include: Case Reference ({case_id}),
the list of required documents: {requested_documents},
a note that the case cannot proceed until documents are received,
and a link to upload documents: {tracking_link}
""",
    },
    "FRAUD_REVIEW_STARTED": {
        "subject_template": "{case_id} | Additional Verification In Progress",
        "instruction": """
Generate an email informing the customer that their case is undergoing additional security verification.
IMPORTANT: NEVER use the words 'fraud', 'suspicious', 'risk', or 'score'.
Use phrases like 'enhanced security review', 'additional verification steps', 'standard security protocols'.
Include: Case Reference ({case_id}),
a note that no customer action is required,
and that this verification helps protect their account.
Include the tracking link: {tracking_link}
""",
    },
    "EVIDENCE_REVIEW_COMPLETED": {
        "subject_template": "{case_id} | Document Review Completed",
        "instruction": """
Generate an update email informing the customer that their submitted documents have been reviewed.
Include: Case Reference ({case_id}),
confirmation that documents have been successfully reviewed,
a note that the case is proceeding to the next stage of review,
and an estimated resolution timeline of 3-5 business days.
Include the tracking link: {tracking_link}
""",
    },
    "CASE_RESOLVED": {
        "subject_template": "{case_id} | Dispute Resolution Completed",
        "instruction": """
Generate a resolution email informing the customer that their dispute has been resolved.
Include: Case Reference ({case_id}),
Final Status: {resolution_status},
Resolution Summary: {resolution_summary},
a thank-you message for their patience,
and the tracking link to view full details: {tracking_link}
""",
    },
    "STATUS_CHANGED": {
        "subject_template": "{case_id} | Case Status Update",
        "instruction": """
Generate a status update email informing the customer that their dispute status has changed.
Include: Case Reference ({case_id}),
New Status: {new_status},
a brief explanation of what this status means for the customer,
and the tracking link: {tracking_link}
""",
    },
}


def build_generation_prompt(
    notification_type: str,
    case_data: dict,
    context: dict | None = None,
) -> str:
    """Build the human-turn prompt for the LLM from case data and notification type."""
    ctx = context or {}
    case_id       = case_data.get("case_id", "N/A")
    amount        = case_data.get("amount", 0)
    currency      = case_data.get("currency", "INR")
    merchant      = case_data.get("merchant", "the merchant")
    status        = case_data.get("status", "Under Review")
    tracking_link = f"http://localhost:3000/track/{case_id}"

    template = NOTIFICATION_TEMPLATES.get(notification_type, NOTIFICATION_TEMPLATES["STATUS_CHANGED"])
    subject  = template["subject_template"].format(case_id=case_id)
    instr    = template["instruction"].format(
        case_id             = case_id,
        amount              = f"{amount:,.2f}",
        currency            = currency,
        merchant            = merchant,
        status              = status,
        tracking_link       = tracking_link,
        requested_documents = ", ".join(ctx.get("requested_documents", [])) or "relevant supporting documents",
        resolution_status   = ctx.get("resolution_status", status),
        resolution_summary  = ctx.get("resolution_summary", "Your case has been reviewed and a decision has been reached."),
        new_status          = ctx.get("new_status", status),
    )

    return f"""DISPUTE CASE DETAILS:
  Case ID           : {case_id}
  Customer Name     : {case_data.get("customer_name", "Valued Customer")}
  Amount            : {currency} {amount:,.2f}
  Merchant          : {merchant}
  Transaction Type  : {case_data.get("transaction_type", "")}
  Current Status    : {status}
  Dispute Category  : {case_data.get("dispute_category", "")}

NOTIFICATION TYPE: {notification_type}
PRE-FILLED SUBJECT: {subject}

INSTRUCTION:
{instr.strip()}

Generate the email now. Return ONLY valid JSON with keys "subject" and "body"."""
