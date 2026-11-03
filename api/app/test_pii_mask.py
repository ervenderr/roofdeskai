import pytest

from .engine.mask import mask

UNCHANGED = [
    "user@", "@handle", "12345", "1234567",
    "00000000-0000-0000-0000-000000000001",
    "2026-11-04", "2026-11-04 12:30", "2026-11-04T12:30:05",
    "1730000000", "172.18.0.12", "172.18.0.12:5432", "1.2.3", "0.27.1",
]


@pytest.mark.parametrize("s", UNCHANGED)
def test_non_pii_unchanged(s):
    assert mask(s) == s
    assert mask(f"seen {s} in the log, ok") == f"seen {s} in the log, ok"


@pytest.mark.parametrize("s", [
    "+41 44 123 45 67", "(303) 555-0142", "303-555-0142", "303.555.0142", "+1 303 555 0142",
])
def test_phones_masked(s):
    assert mask(s) == "[phone]"
    assert mask(f"call {s} now") == "call [phone] now"


def test_emails():
    assert mask("a@b.com and c.d@e.org") == "[email] and [email]"
    assert mask("a.b+c@x.co.uk") == "[email]"


def test_unicode_name_kept():
    assert mask("Jürgen Müller <j.mueller@bsp.ch>") == "Jürgen Müller <[email]>"


def test_idempotent():
    s = "[email] / [phone]"
    assert mask(s) == s
    assert mask(mask("a@b.com +41 44 123 45 67")) == "[email] [phone]"


def test_non_str_and_failure(monkeypatch):
    assert mask(123) == "123"
    assert mask(None) == "None"
    from .engine import mask as m
    monkeypatch.setattr(m, "_TOKEN", None)
    assert mask("a@b.com") == "[unmasked-failed]"
