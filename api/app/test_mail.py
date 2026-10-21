import pytest

from . import mailer, replies
from .config import settings

BOUNCE = (b"From: MAILER-DAEMON@x.com\nTo: hello@leadpilot.example\nSubject: Undelivered\nMIME-Version: 1.0\n"
          b"Content-Type: multipart/report; report-type=delivery-status; boundary=B\n\n"
          b"--B\nContent-Type: text/plain\n\nfailed\n--B\nContent-Type: message/delivery-status\n\n"
          b"Reporting-MTA: dns; x.com\n\nFinal-Recipient: rfc822; gone@biz.test\nAction: failed\n\n--B--\n")


def test_parse_reply_and_bounce(monkeypatch):
    monkeypatch.setattr(settings, "sender_email", "hello@leadpilot.example")
    assert replies.parse(b"From: Bob <bob@biz.test>\nSubject: Re: hi\n\nSounds good\n") == ("bob@biz.test", "reply", "Sounds good")
    assert replies.parse(BOUNCE) == ("gone@biz.test", "bounce", "")
    assert replies.parse(b"From: hello@leadpilot.example\n\nself\n") is None


def test_smtp_send(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout): sent.append((host, port))
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): sent.append("tls")
        def login(self, u, p): sent.append(("login", u))
        def send_message(self, m): sent.append(m)

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "mail_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_user", "me@gmail.com")
    mailer.send("a@b.co", "Hi", "Body")
    msg = sent[-1]
    assert sent[1] == "tls" and msg["To"] == "a@b.co" and "List-Unsubscribe" in msg and msg["Message-ID"]


def test_smtp_failure_is_mail_error(monkeypatch):
    def boom(*a, **k): raise OSError("down")
    monkeypatch.setattr(mailer.smtplib, "SMTP", boom)
    monkeypatch.setattr(settings, "mail_transport", "smtp")
    with pytest.raises(mailer.MailError):
        mailer.send("a@b.co", "Hi", "Body")


def test_quoted_footer_is_not_part_of_the_reply(monkeypatch):
    monkeypatch.setattr(settings, "sender_email", "hello@leadpilot.example")
    raw = (b"From: Bob <bob@biz.test>\nSubject: Re: hi\n\nYes interested\n\n"
           b"On Wed, Oct 21, 2026 at 12:49 PM The LeadPilot team <hello@leadpilot.example> wrote:\n"
           b"> Hi there\n> Not interested? Reply \"unsubscribe\" and I won't contact you again.\n")
    assert replies.parse(raw) == ("bob@biz.test", "reply", "Yes interested")


def test_html_email_escapes_and_has_footer(monkeypatch):
    from . import email_html
    monkeypatch.setattr(settings, "sender_address", "1 Test St")
    out = email_html.render("Hi <b>team</b>,\n\nHello.", "Subj", 1, ["Does a thing"])
    assert "&lt;b&gt;team" in out and "<b>team" not in out
    assert "Does a thing" in out and "mailto:" in out and "1 Test St" in out and "unsubscribe" in out
    assert "What it does" not in email_html.render("Hi", "S", 2, ["Does a thing"])
