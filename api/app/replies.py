"""Poll the outreach mailbox over IMAP and feed replies and bounces to outreach.handle_event.
Matching is by sender address (handle_event ignores addresses that are not prospects)."""
import email
import imaplib
import logging
from email import policy
from email.message import Message
from email.utils import parseaddr

from . import outreach
from .config import settings

log = logging.getLogger("leadpilot.replies")


def _text(msg: Message) -> str:
    part = msg.get_body(preferencelist=("plain",))
    return part.get_content() if part else ""


def parse(raw: bytes) -> tuple[str, str, str] | None:
    """Return (prospect email, kind, body), or None for mail we cannot attribute."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    if msg.get_content_type() == "multipart/report":  # delivery-status notice: the failed address is inside it
        for part in msg.walk():
            if part.get_content_type() == "message/delivery-status":
                for block in part.get_payload():
                    rcpt = block.get("Final-Recipient")
                    if rcpt:
                        return rcpt.split(";")[-1].strip(), "bounce", ""
        return None
    sender = parseaddr(str(msg.get("From", "")))[1]
    if not sender or sender.lower() == settings.sender_email.lower():
        return None
    return sender, "reply", _text(msg)


def poll() -> dict:
    result = {"seen": 0, "matched": 0, "ignored": 0}
    with imaplib.IMAP4_SSL(settings.imap_host) as imap:
        imap.login(settings.smtp_user, settings.smtp_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _, parts = imap.fetch(num, "(RFC822)")  # fetching marks it read, so it is processed once
            result["seen"] += 1
            parsed = parse(parts[0][1])
            if parsed and outreach.handle_event(*parsed).get("matched"):
                result["matched"] += 1
            else:
                result["ignored"] += 1
    log.info("reply poll: %s", result)
    return result
