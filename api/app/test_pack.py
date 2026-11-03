import copy
import subprocess
import sys

import pytest
import yaml
from sqlalchemy import text

from . import db, llm
from .config import settings
from .pack import PackError, get_pack, load_pack, render

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


# ---- roofing pack golden tests ----
from . import agent, faq, policy, tools  # noqa: E402
from .tests_data import frozen_old as F  # noqa: E402


def _check(p, o):
    q = p.qualification
    assert set(q.service_area) == set(o["area"]) and len(q.service_area) == len(o["area"])
    assert set(q.qualifying_services) == set(o["qual"])
    assert q.max_timeline_months == o["months"]
    assert q.owner_yes_pattern == o["yes"] and q.owner_no_pattern == o["no"] and q.non_business_pattern == o["nonbiz"]
    assert {k.value: v for k, v in q.service_synonyms.items()} == o["service"]
    assert list(q.service_synonyms) and [k.value for k in q.service_synonyms] == list(o["service"])
    assert p.escalation.safety == o["escalation"]["safety"]
    m = p.messages
    assert m.ask == o["ask"] and m.safe_fallback == o["fallback"]
    assert m.closed == o["closed"] and m.disqualify == o["disq"] and m.nurture == o["nurture"] and m.no_slots == o["noslots"]
    assert tuple((e.source, e.text) for e in p.faq) == tuple(o["faq"])
    assert tuple(p.calendar.slot_hours) == tuple(o["hours"]) and p.calendar.days_ahead == o["days"]
    assert q.extra_stopwords | (set(o["generic"]) - {"roof", "roofing", "summit"}) == set(o["generic"])
    assert set(q.extra_stopwords) == {"roof", "roofing", "summit"}


def _live():
    return dict(area=policy.SERVICE_AREA, qual=policy.QUALIFYING_SERVICES, months=policy.MAX_TIMELINE_MONTHS,
                yes=policy._OWN_YES, no=policy._OWN_NO, nonbiz=policy._NON_ROOF, service=policy._SERVICE,
                escalation=policy._ESCALATION_PATTERNS, ask=policy.ASK, fallback=policy.SAFE_FALLBACK,
                closed=agent.CLOSED_REPLY, disq=agent.DISQUALIFY_REPLY, nurture=agent.NURTURE_REPLY,
                noslots=agent.NO_SLOTS_REPLY, faq=faq.FAQ, hours=tools.SLOT_HOURS, days=tools.SLOT_DAYS_AHEAD,
                generic=policy._GENERIC)


def _frozen():
    return dict(area=F.FROZEN_SERVICE_AREA, qual=F.FROZEN_QUALIFYING_SERVICES, months=F.FROZEN_MAX_TIMELINE_MONTHS,
                yes=F.FROZEN_OWN_YES, no=F.FROZEN_OWN_NO, nonbiz=F.FROZEN_NON_ROOF, service=F.FROZEN_SERVICE,
                escalation=F.FROZEN_ESCALATION, ask=F.FROZEN_ASK, fallback=F.FROZEN_SAFE_FALLBACK,
                closed=F.FROZEN_CLOSED_REPLY, disq=F.FROZEN_DISQUALIFY_REPLY, nurture=F.FROZEN_NURTURE_REPLY,
                noslots=F.FROZEN_NO_SLOTS_REPLY, faq=F.FROZEN_FAQ, hours=F.FROZEN_SLOT_HOURS,
                days=F.FROZEN_SLOT_DAYS_AHEAD, generic=F.FROZEN_GENERIC)


def test_golden_live(roofing_pack):
    _check(roofing_pack, _live())  # removed in plan 03-03 when the old constants go


def test_golden_frozen(roofing_pack):
    _check(roofing_pack, _frozen())


def test_golden_always_human_matches_client_profile(roofing_pack):
    prof = yaml.safe_load((settings.clients_dir / "summit-roofing.yaml").read_text())
    assert list(roofing_pack.escalation.always_human) == prof["always_human"]


def test_templates_exact(roofing_pack):
    m = roofing_pack.messages
    assert m.qualified_prefix == "Good news, you qualify for a free roof inspection! "
    assert m.slot_unavailable_prefix == "Sorry, that time isn't available. "
    assert m.customer_intro == "Hi {name},\n\nYour free roof inspection is booked for {when}.\n\n"
    assert m.owner_alert_body == ("{name} booked a free roof inspection for {when}.\nPhone: {phone}\n"
                                  "Email: {email}\nAddress: {address}\nNeed: {need}")
    assert m.pick_prompt == "Which of those openings works for you? Just say first, second, and so on."
    assert m.offer_slots.format(prefix="P ", options="O") == "P Here are the next openings: O. Which one works for you?"
    assert m.booked.format(when="W") == "You're booked for W. We'll see you then!"


def test_get_pack_default():
    assert get_pack().slug == "summit-roofing"


def test_cli_ok():
    r = subprocess.run([sys.executable, "-m", "app.pack", "summit-roofing"], capture_output=True, text=True)
    assert r.returncode == 0 and "summit-roofing" in r.stdout


SAMPLE = {"<<asked>>": "which?", "<<known>>": "{}", "<<faq>>": "- a"}


def _fill(body):
    for k, v in SAMPLE.items():
        body = body.replace(k, v)
    return body


def test_render_agent(roofing_pack):
    assert render(llm.load_prompt("agent.v2")[1], roofing_pack) == F.FROZEN_AGENT_V2


def test_render_faq(roofing_pack):
    assert render(llm.load_prompt("faq-answer.v1")[1], roofing_pack) == F.FROZEN_FAQ_ANSWER_V1


def test_render_full_message(roofing_pack):
    got = _fill(render(llm.load_prompt("agent.v2")[1], roofing_pack))
    assert got == _fill(F.FROZEN_AGENT_V2) and "{{" not in got


def test_render_unknown_placeholder(roofing_pack):
    with pytest.raises(PackError, match="typo"):
        render("hi {{typo}}", roofing_pack)


def test_render_prompt_version_headers():
    assert llm.load_prompt("agent.v2")[0] == "agent.v2"
    assert llm.load_prompt("faq-answer.v1")[0] == "faq-answer.v1"


def test_render_service_enum(roofing_pack):
    assert render("{{service_enum}}", roofing_pack) == '"repair" | "replacement" | "inspection" | "other"'


@pytest.mark.parametrize("field", ["business", "kind", "offer"])
@pytest.mark.parametrize("bad", ["{{x}}", "<<faq>>"])
def test_meta_rejects_tokens(biz, field, bad):
    write_pack(biz, _mut("pack", lambda p: p.update({field: bad})))
    with pytest.raises(PackError, match="pack.yaml"):
        load_pack(SLUG)


def test_seed_faq_from_pack(monkeypatch):
    tid = "00000000-0000-0000-0000-0000000000c3"
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES "
                       "(:t, 'test-faqpack', 'F', 'UTC', 'summit-roofing') ON CONFLICT DO NOTHING"), {"t": tid})
    monkeypatch.setattr(faq.llm, "embed", lambda t: [0.1] * 384)
    faq.seed_faq(tid, reload=True)
    with db.system() as c:
        rows = [tuple(r) for r in c.execute(text("SELECT source, text FROM faq_chunks WHERE tenant_id=:t ORDER BY id"), {"t": tid})]
    assert rows == [(e.source, e.text) for e in get_pack(tid).faq]


def test_faq_seed_sql_matches_pack(roofing_pack):
    import re
    from pathlib import Path
    sql = Path("/srv/db/faq_seed.sql")
    if not sql.exists():
        pytest.skip("/srv/db is not mounted in this container")
    rows = re.findall(r"INSERT INTO public\.faq_chunks \(id, source, text, embedding\) VALUES \(\d+, '((?:[^']|'')*)', '((?:[^']|'')*)', '",
                      sql.read_text())
    rows = [(a.replace("''", "'"), b.replace("''", "'")) for a, b in rows]
    assert rows == [(e.source, e.text) for e in roofing_pack.faq]


def test_handle_turn_missing_pack():
    tid = "00000000-0000-0000-0000-0000000000c1"
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES "
                       "(:t, 'test-nopack', 'N', 'UTC', NULL) ON CONFLICT DO NOTHING"), {"t": tid})
    with pytest.raises(PackError):
        agent.handle_turn("hello", tenant_id=tid)
