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


# --- PiiMaskFilter ---
import logging

from .logctx import PiiMaskFilter, TenantFilter


def _rec(msg, args=(), exc_info=None):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, exc_info)


def test_filter_masks_msg_and_args_keeps_shape():
    r = _rec("lead %s at %s n=%d", ("a@b.com", "+41 44 123 45 67", 3))
    assert PiiMaskFilter().filter(r) is True
    assert r.args == ("[email]", "[phone]", 3)
    assert r.getMessage() == "lead [email] at [phone] n=3"


def test_filter_mapping_args_not_mutated():
    orig = {"e": "a@b.com", "n": 1}
    r = _rec("x %(e)s %(n)d", orig)
    PiiMaskFilter().filter(r)
    assert r.getMessage() == "x [email] 1"
    assert orig["e"] == "a@b.com"


def test_filter_masks_msg_text():
    r = _rec("mail a@b.com")
    PiiMaskFilter().filter(r)
    assert r.msg == "mail [email]"


def test_filter_uvicorn_access_formatter():
    from uvicorn.logging import AccessFormatter

    args = ("172.18.0.12:5432", "GET", "/leads?email=a@b.com", "1.1", 200)
    r = _rec('%s - "%s %s HTTP/%s" %d', args)
    assert PiiMaskFilter().filter(r) is True
    out = AccessFormatter(fmt="%(client_addr)s %(request_line)s %(status_code)s", use_colors=False).format(r)
    assert "[email]" in out and "172.18.0.12" in out and "200" in out and "a@b.com" not in out


def test_filter_masks_traceback():
    try:
        raise ValueError("bad a@b.com")
    except ValueError:
        import sys
        r = _rec("boom", (), sys.exc_info())
    PiiMaskFilter().filter(r)
    out = logging.Formatter().format(r)
    assert "[email]" in out and "a@b.com" not in out


def test_filter_bad_format_does_not_raise():
    r = _rec("x %s %s a@b.com", ("a@b.com",))
    assert PiiMaskFilter().filter(r) is True
    assert "a@b.com" not in r.msg and r.args == ("[email]",)


def test_filter_failure_withholds(monkeypatch):
    from . import logctx
    monkeypatch.setattr(logctx, "mask", lambda s: (_ for _ in ()).throw(RuntimeError("x")))
    r = _rec("a@b.com", ("a@b.com",))
    assert PiiMaskFilter().filter(r) is True
    assert r.msg == "[log withheld]" and r.args == ()


def test_main_installs_filters():
    from . import main
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not lg.handlers:
            lg.addHandler(logging.NullHandler())
    main.install_log_filters()
    main.install_log_filters()  # idempotent
    for h in logging.getLogger().handlers:
        assert sum(isinstance(f, TenantFilter) for f in h.filters) == 1
        assert sum(isinstance(f, PiiMaskFilter) for f in h.filters) == 1
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            assert sum(isinstance(f, PiiMaskFilter) for f in h.filters) == 1
