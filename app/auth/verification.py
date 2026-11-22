"""Email verification challenge delivery over authenticated TLS SMTP."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings


def send_verification_email(email: str, token: str, settings: Settings) -> bool:
    if not settings.smtp_host or not settings.smtp_from:
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = email
    msg["Subject"] = "SmartCampus AI - Verify your email"
    msg.set_content(
        "Verify your SmartCampus AI account by sending this one-time token to "
        "POST /api/v1/candidates/verify-email (field: token):\n\n"
        + token
        + "\n\nThe token expires in 24 hours. Never share your password.\n"
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(msg)
    return True
