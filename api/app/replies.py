"""Poll the outreach mailbox over IMAP and feed replies and bounces to outreach.handle_event.
Matching is by sender address (handle_event ignores addresses that are not prospects)."""
import email
import imaplib
import logging
import re
from email import policy
from email.message import Message
from email.utils import parseaddr

from . import mailer, outreach
from .config import settings

log = logging.getLogger("leadpilot.replies")


QUOTE_START = re.compile(r"^(On .{5,200}wrote:|-{2,} ?Original Message|From: .+)$|^>", re.M | re.S)


def _text(msg: Message) -> str:
    """Only what the prospect wrote: our own quoted footer ('reply unsubscribe') must never be classified."""
    part = msg.get_body(preferencelist=("plain",))
    body = part.get_content() if part else ""
    m = QUOTE_START.search(body)
    return (body[:m.start()] if m else body).strip()


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


def interested_draft(name: str) -> str:
    """Ready-to-paste answer to a yes: the demo, the video, the price and one next step."""
    return (f"Hi {name} team,\n\nThanks for the reply. Here is the assistant working on a sample roofing company: "
            f"{settings.demo_url}\nA 45-second walkthrough: {settings.demo_url}/showcase\n\n"
            f"The pilot is free for {settings.pilot_days} days. After that it is ${settings.monthly_price_usd}/month with "
            "no setup fee and no contract; cancel any time.\n\n"
            "If you want it on your own site, reply with your service area and the phone number customers should be sent to, "
            "and I will set it up.\n\nThe RoofDesk AI team")


def notify_owner(outcome: dict) -> None:
    """Email the owner about a reply that needs a person. A failed alert never loses the reply."""
    if not settings.owner_email:
        return
    subject = f"{outcome.get('name', 'A prospect')} replied ({outcome.get('label')})".replace("\n", " ")[:100]
    body = (f"Prospect: {outcome.get('name')}\nClassified as: {outcome.get('label')}\nStatus: {outcome.get('status')}\n\n"
            "Reply to them from your outreach mailbox.")
    if outcome.get("label") == "interested":
        body += "\n\nSuggested reply:\n\n" + interested_draft(outcome.get("name", "there"))
    try:
        mailer.send(settings.owner_email, subject, body)
    except mailer.MailError:
        log.exception("reply saved but the owner alert failed")


def poll() -> dict:
    result = {"seen": 0, "matched": 0, "ignored": 0, "replies": []}
    with imaplib.IMAP4_SSL(settings.imap_host) as imap:
        imap.login(settings.smtp_user, settings.smtp_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _, parts = imap.fetch(num, "(RFC822)")  # fetching marks it read, so it is processed once
            result["seen"] += 1
            parsed = parse(parts[0][1])
            outcome = outreach.handle_event(*parsed) if parsed else {}
            if outcome.get("matched"):
                result["matched"] += 1
                result["replies"].append(outcome)
                if outcome.get("needs_human"):
                    notify_owner(outcome)
            else:
                result["ignored"] += 1
    log.info("reply poll: %s", result)
    return result
