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
    "DOCUMENTS_RECEIVED": {
        "subject_template": "{case_id} | Documents Received",
        "instruction": """
Generate a confirmation email informing the customer that their uploaded documents have been received.
Include: Case Reference ({case_id}),
confirmation that the documents have been successfully received and added to their case,
a note that the documents will be reviewed by the team shortly,
and the tracking link: {tracking_link}
""",
    },
}


def build_html_email(
    notification_type: str,
    case_data: dict,
    context: dict | None = None,
) -> tuple[str, str]:
    """
    Build a professional HTML email directly from templates — no LLM dependency.
    Returns (subject, html_body).
    """
    ctx        = context or {}
    case_id    = case_data.get("case_id", "N/A")
    name       = case_data.get("customer_name", "Valued Customer")
    amount     = case_data.get("amount", 0)
    currency   = case_data.get("currency", "INR")
    merchant   = case_data.get("merchant", "—")
    txn_type   = case_data.get("transaction_type", "")
    tracking   = f"http://localhost:3000/track/{case_id}"

    tpl        = NOTIFICATION_TEMPLATES.get(notification_type, NOTIFICATION_TEMPLATES["STATUS_CHANGED"])
    subject    = tpl["subject_template"].format(case_id=case_id)

    # ── per-type badge + headline + body paragraphs ─────────────────────────
    if notification_type == "CASE_RECEIVED":
        badge      = ("#EBF5FF", "#1a5f9e", "DISPUTE RECEIVED")
        headline   = "Your dispute has been received"
        paragraphs = [
            f"Dear {name},",
            f"We have successfully received your dispute and assigned it a unique reference number. "
            f"Our dedicated Dispute Resolution team will begin the review process within 1 business day.",
            "You do not need to take any further action at this time. We will keep you informed at every stage of the process.",
        ]

    elif notification_type == "INVESTIGATION_STARTED":
        badge      = ("#F3F0FF", "#6B46C1", "UNDER INVESTIGATION")
        headline   = "Your case is now under active investigation"
        paragraphs = [
            f"Dear {name},",
            "Good news — our Dispute Resolution team has commenced a detailed investigation into your case. "
            "Our specialists are reviewing all available transaction records and relevant information.",
            "No action is required from you at this time. We expect to complete our investigation within "
            "<strong>5–7 business days</strong> and will notify you of any updates.",
        ]

    elif notification_type == "DOCUMENT_REQUESTED":
        docs       = ctx.get("requested_documents", [])
        doc_list   = "".join(f"<li style='margin:4px 0;color:#475569;font-size:14px;'>{d}</li>" for d in docs) if docs else \
                     "<li style='margin:4px 0;color:#475569;font-size:14px;'>Supporting documents relevant to your dispute</li>"
        badge      = ("#FFFBEB", "#D97706", "ACTION REQUIRED")
        headline   = "Additional documents are required"
        paragraphs = [
            f"Dear {name},",
            "To continue processing your dispute, our team requires the following supporting documents:",
            f"<ul style='margin:12px 0;padding-left:20px;'>{doc_list}</ul>",
            "Please upload the documents using the link below. Your case cannot proceed until the required documents are received.",
        ]

    elif notification_type == "FRAUD_REVIEW_STARTED":
        badge      = ("#EEF2FF", "#4338CA", "VERIFICATION IN PROGRESS")
        headline   = "Additional security verification in progress"
        paragraphs = [
            f"Dear {name},",
            "As part of our standard security protocols, your case is currently undergoing an enhanced security review. "
            "This additional verification step is designed to protect your account and ensure a thorough investigation.",
            "No action is required from you. This process typically completes within <strong>2–3 business days</strong>. "
            "We will notify you as soon as the verification is complete.",
        ]

    elif notification_type == "EVIDENCE_REVIEW_COMPLETED":
        badge      = ("#F0FDF4", "#16A34A", "DOCUMENTS REVIEWED")
        headline   = "Your documents have been reviewed"
        paragraphs = [
            f"Dear {name},",
            "We are pleased to inform you that all documents submitted for your dispute have been successfully reviewed "
            "and verified by our team.",
            "Your case is now proceeding to the next stage of our review process. "
            "We anticipate a final resolution within <strong>3–5 business days</strong>.",
        ]

    elif notification_type == "CASE_RESOLVED":
        res_status  = ctx.get("resolution_status", case_data.get("status", "Resolved"))
        res_summary = ctx.get("resolution_summary", "Your case has been reviewed and a decision has been reached.")
        is_resolved = "resolved" in res_status.lower() or "favour" in res_status.lower()
        badge       = ("#F0FDF4", "#16A34A", "CASE RESOLVED") if is_resolved else ("#FFF7ED", "#EA580C", "CASE CLOSED")
        headline    = "Your dispute has been resolved"
        paragraphs  = [
            f"Dear {name},",
            f"We have completed our investigation into your dispute. <strong>Resolution: {res_status}</strong>.",
            res_summary,
            "Thank you for your patience throughout this process. We value your trust in SecureBank and are committed to providing you with the highest level of service.",
        ]

    elif notification_type == "DOCUMENTS_RECEIVED":
        badge      = ("#F0FDF4", "#16A34A", "DOCUMENTS RECEIVED")
        headline   = "We have received your documents"
        paragraphs = [
            f"Dear {name},",
            "Thank you for submitting your documents. We have successfully received and attached them to your dispute case.",
            "Our team will review the submitted documents and you will be notified of any further updates. "
            "No additional action is required from you at this time.",
        ]

    else:  # STATUS_CHANGED / fallback
        new_status = ctx.get("new_status", case_data.get("status", "Under Review"))
        badge      = ("#F1F5F9", "#475569", "STATUS UPDATE")
        headline   = "Your dispute status has been updated"
        paragraphs = [
            f"Dear {name},",
            f"We would like to inform you that the status of your dispute case has been updated to "
            f"<strong>{new_status}</strong>.",
            "Our team continues to work diligently on your case. You can track real-time progress using the link below.",
        ]

    # ── case details table rows ───────────────────────────────────────────────
    detail_rows = f"""
        <tr>
          <td style="padding:7px 0;color:#94A3B8;font-size:13px;width:150px;vertical-align:top;">Case Reference</td>
          <td style="padding:7px 0;color:#0F2A4A;font-size:13px;font-weight:700;">{case_id}</td>
        </tr>
        <tr>
          <td style="padding:7px 0;color:#94A3B8;font-size:13px;vertical-align:top;">Transaction</td>
          <td style="padding:7px 0;color:#0F2A4A;font-size:13px;">{currency} {amount:,.2f} &nbsp;·&nbsp; {merchant}</td>
        </tr>
        {"" if not txn_type else f'<tr><td style="padding:7px 0;color:#94A3B8;font-size:13px;vertical-align:top;">Type</td><td style="padding:7px 0;color:#0F2A4A;font-size:13px;">{txn_type}</td></tr>'}
    """

    badge_bg, badge_color, badge_text = badge
    para_html = "".join(
        f'<p style="color:#475569;font-size:14px;line-height:1.75;margin:0 0 14px;">{p}</p>'
        for p in paragraphs
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#EEF2F7;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F7;padding:48px 16px;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg,#0F2A4A 0%,#1a4a7a 100%);padding:24px 40px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <div style="font-size:11px;color:#7FB3D3;letter-spacing:1.5px;text-transform:uppercase;">Dispute Resolution Centre</div>
              </td>
              <td align="right">
                <div style="font-size:11px;color:#7FB3D3;">Ref: {case_id}</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Status banner -->
      <tr>
        <td style="background:#F8FAFC;border-bottom:1px solid #E2E8F0;padding:14px 40px;">
          <span style="display:inline-block;background:{badge_bg};color:{badge_color};
                       font-size:11px;font-weight:700;letter-spacing:1px;
                       padding:4px 14px;border-radius:20px;text-transform:uppercase;">{badge_text}</span>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:36px 40px 24px;">
          <h2 style="margin:0 0 20px;color:#0F2A4A;font-size:20px;font-weight:700;line-height:1.3;">{headline}</h2>
          {para_html}
        </td>
      </tr>

      <!-- Case details box -->
      <tr>
        <td style="padding:0 40px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;">
            <tr><td style="padding:20px 24px;">
              <div style="font-size:11px;font-weight:700;color:#94A3B8;letter-spacing:1px;
                          text-transform:uppercase;margin-bottom:12px;">Case Details</div>
              <table width="100%" cellpadding="0" cellspacing="0">
                {detail_rows}
              </table>
            </td></tr>
          </table>
        </td>
      </tr>

      <!-- CTA button -->
      <tr>
        <td style="padding:0 40px 36px;">
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="background:#1a5f9e;border-radius:6px;">
                <a href="{tracking}"
                   style="display:block;color:#ffffff;text-decoration:none;
                          font-size:14px;font-weight:600;padding:13px 28px;
                          letter-spacing:0.3px;">Track Your Dispute &rarr;</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#F8FAFC;border-top:1px solid #E2E8F0;padding:20px 40px;">
          <p style="margin:0;color:#94A3B8;font-size:11px;line-height:1.7;">
            This is an automated notification from SecureBank Dispute Resolution Centre.
            Please do not reply directly to this email.<br>
            For assistance, quote your case reference <strong style="color:#64748B;">{case_id}</strong>
            and contact us via our official helpline or nearest branch.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    return subject, html


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

