import copy
import subprocess
import sys

import pytest
import yaml
from sqlalchemy import text

from . import db
from .config import settings
from .pack import PackError, get_pack, load_pack

SLUG = "demo-biz"
MIN_PACK = {
    "pack": {"slug": SLUG, "business": "Demo Biz", "kind": "a demo company", "offer": "books demos",
             "timezone": "America/Denver"},
    "calendar": {"timezone": "Etc/UTC", "slot_hours": [9, 11], "slot_minutes": 60, "days_ahead": 14,
                 "weekdays_only": True, "buffer_minutes": 0},
    "qualification": {"service_area": ["denver"], "qualifying_services": ["repair"], "max_timeline_months": 6,
                      "service_synonyms": {"repair": "fix", "inspection": "look"},
                      "non_business_pattern": "gutter", "owner_yes_pattern": "yes", "owner_no_pattern": "rent",
                      "extra_stopwords": ["demo"]},
    "escalation": {"safety": r"\bfire\b", "always_human": ["complaint"]},
    "messages": {
        "closed": {"DONE": "d", "DISQUALIFY": "q", "ESCALATE": "e"},
        "disqualify": "no", "nurture": "later", "no_slots": "none", "safe_fallback": "unknown",
        "qualified_prefix": "Good news. ", "slot_unavailable_prefix": "Sorry. ", "pick_prompt": "Pick one.",
        "offer_slots": "{prefix}Openings: {options}.", "booked": "Booked {when}.", "anything_else": "Anything else?",
        "ask": {"service_type": "s?", "is_owner": "o?", "address": "a?", "timeline_months": "t?", "name": "n?",
                "phone or email": "p?"},
        "owner_alert_subject": "New {name} ({when})",
        "owner_alert_body": "{name} {when} {phone} {email} {address} {need}",
        "customer_subject": "Booked {when}", "customer_intro": "Hi {name}, {when}.\n\n",
        "followup_subject": "Hello from {business}", "followup_body": "{greeting}\n\n{business}",
    },
    "faq": {"entries": [{"source": "hours", "text": "9 to 5."}]},
}


def write_pack(root, data=None, slug=SLUG, raw=None):
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    for name, body in (data or MIN_PACK).items():
        (d / f"{name}.yaml").write_text(yaml.safe_dump(body, sort_keys=False))
    for name, body in (raw or {}).items():
        if body is None:
            (d / f"{name}.yaml").unlink()
        else:
            (d / f"{name}.yaml").write_text(body)
    return d


@pytest.fixture
def biz(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "businesses_dir", tmp_path)
    return tmp_path


def _mut(file, fn):
    data = copy.deepcopy(MIN_PACK)
    fn(data[file])
    return data


def test_minimal_pack_loads(biz):
    write_pack(biz)
    p = load_pack(SLUG)
    assert p.slug == SLUG and p.meta.business == "Demo Biz" and len(p.hash) == 64


# (file, mutation, expected field in message)
CASES = {
    "unknown_key": ("calendar", lambda c: c.update(bogus=1), "bogus"),
    "missing_field": ("qualification", lambda q: q.pop("max_timeline_months"), "max_timeline_months"),
    "bad_regex": ("escalation", lambda e: e.update(safety="(unclosed"), "safety"),
    "bad_tz": ("calendar", lambda c: c.update(timezone="Mars/Base"), "timezone"),
    "hours_not_increasing": ("calendar", lambda c: c.update(slot_hours=[11, 9]), "slot_hours"),
    "hours_out_of_range": ("calendar", lambda c: c.update(slot_hours=[9, 25]), "slot_hours"),
    "template_unknown_field": ("messages", lambda m: m.update(booked="Booked {whenn}."), "booked"),
    "template_positional": ("messages", lambda m: m.update(nurture="hi {}"), "nurture"),
    "template_stray_brace": ("messages", lambda m: m.update(nurture="hi {"), "nurture"),
    "ask_missing_key": ("messages", lambda m: m["ask"].pop("name"), "ask"),
    "closed_missing_key": ("messages", lambda m: m["closed"].pop("DONE"), "closed"),
    "service_area_not_lower": ("qualification", lambda q: q.update(service_area=["Denver"]), "service_area"),
}


@pytest.mark.parametrize("case", CASES)
def test_malformed(biz, case):
    file, fn, field = CASES[case]
    write_pack(biz, _mut(file, fn))
    with pytest.raises(PackError) as e:
        load_pack(SLUG)
    assert f"{file}.yaml" in str(e.value) and field in str(e.value)


def test_malformed_missing_file(biz):
    write_pack(biz, raw={"calendar": None})
    with pytest.raises(PackError, match="calendar.yaml"):
        load_pack(SLUG)


def test_malformed_empty_yaml(biz):
    write_pack(biz, raw={"faq": ""})
    with pytest.raises(PackError, match="faq.yaml"):
        load_pack(SLUG)


def test_malformed_invalid_yaml(biz):
    write_pack(biz, raw={"faq": "entries: [unclosed"})
    with pytest.raises(PackError, match="faq.yaml"):
        load_pack(SLUG)


@pytest.mark.parametrize("slug", ["../x", "Bad_Slug", "a/b", ""])
def test_malformed_slug(biz, slug):
    with pytest.raises(PackError, match="slug"):
        load_pack(slug)


def test_malformed_slug_folder_mismatch(biz):
    data = _mut("pack", lambda p: p.update(slug="other-name"))
    write_pack(biz, data)
    with pytest.raises(PackError, match=r"pack.yaml.*slug"):
        load_pack(SLUG)


def test_malformed_qualifying_not_in_synonyms(biz):
    write_pack(biz, _mut("qualification", lambda q: q.update(qualifying_services=["replacement"])))
    with pytest.raises(PackError, match="qualification.yaml"):
        load_pack(SLUG)


def test_get_pack_missing(biz):
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES "
                       "('00000000-0000-0000-0000-0000000000c1', 'test-nopack', 'N', 'UTC', NULL), "
                       "('00000000-0000-0000-0000-0000000000c2', 'test-badpack', 'B', 'UTC', 'nope') "
                       "ON CONFLICT DO NOTHING"))
    with pytest.raises(PackError, match="pack_slug"):
        get_pack("00000000-0000-0000-0000-0000000000c1")
    with pytest.raises(PackError):
        get_pack("00000000-0000-0000-0000-0000000000c2")


def test_cli_fail():
    r = subprocess.run([sys.executable, "-m", "app.pack", "nope"], capture_output=True, text=True)
    assert r.returncode == 1 and "nope" in r.stderr + r.stdout
