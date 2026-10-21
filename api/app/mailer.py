"""Email transport. MAIL_TRANSPORT=mailpit (dev) or smtp (your own mailbox; Resend bans cold outreach, see docs/deploy.md)."""
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

from .config import settings


class MailError(Exception):
    pass


def _unsub(sender: str) -> str:
    return f"<mailto:{sender}?subject=unsubscribe>"


def _send_mailpit(to: str, subject: str, body: str) -> None:
    try:
        r = httpx.post(f"{settings.mailpit_url}/api/v1/send", timeout=10, json={
            "From": {"Email": settings.sender_email, "Name": settings.sender_name},
            "To": [{"Email": to}], "Subject": subject, "Text": body,
            "Headers": {"List-Unsubscribe": _unsub(settings.sender_email)},
        })
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MailError(type(e).__name__) from e


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = formataddr((settings.sender_name, settings.sender_email))
    msg["To"], msg["Subject"] = to, subject
    msg["Message-ID"] = make_msgid(domain=settings.sender_email.rpartition("@")[2])
    msg["List-Unsubscribe"] = _unsub(settings.sender_email)
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(type(e).__name__) from e


def send(to: str, subject: str, body: str) -> None:
    if settings.mail_transport == "smtp":
        return _send_smtp(to, subject, body)
    return _send_mailpit(to, subject, body)
