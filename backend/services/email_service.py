"""
Email delivery service — Outlook SMTP via TLS.

All emails in demo mode are redirected to NOTIFICATION_EMAIL regardless
of the intended recipient. The `recipient` argument is preserved for logging
and future production use.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.logger import api_logger

_SMTP_SERVER       = os.getenv("SMTP_SERVER", "smtp.office365.com")
_SMTP_PORT         = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USERNAME     = os.getenv("SMTP_USERNAME", "")
_SMTP_PASSWORD     = os.getenv("SMTP_PASSWORD", "")
_NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")


def send_email(subject: str, body: str, recipient: str) -> bool:
    """
    Send an HTML email via Outlook SMTP (TLS).

    In demo mode all mail goes to NOTIFICATION_EMAIL; `recipient` is kept
    for audit purposes only.  Returns True on success, False on any failure.
    Never raises.
    """
    dest = _NOTIFICATION_EMAIL or recipient
    if not dest:
        api_logger.warning("email_service: no destination address — NOTIFICATION_EMAIL not set")
        return False

    if not _SMTP_USERNAME or not _SMTP_PASSWORD:
        api_logger.warning(
            "email_service: SMTP credentials not configured — email not sent "
            f"(would have sent '{subject}' to {dest})"
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = _SMTP_USERNAME
        msg["To"]      = dest
        msg["X-Original-Recipient"] = recipient   # audit header

        msg.attach(MIMEText(body, "html", "utf-8"))

        with smtplib.SMTP(_SMTP_SERVER, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(_SMTP_USERNAME, _SMTP_PASSWORD)
            server.sendmail(_SMTP_USERNAME, [dest], msg.as_string())

        api_logger.info(f"email_service: sent '{subject}' → {dest} (intended: {recipient})")
        return True

    except Exception as exc:
        api_logger.error(f"email_service: failed to send '{subject}' → {dest}: {exc}")
        return False
