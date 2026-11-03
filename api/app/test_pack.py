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
    "qualification": {"rules": [
                          {"id": "service_type", "field": "service_type", "rule": "in_list", "values": ["repair"]},
                          {"id": "is_owner", "field": "is_owner", "rule": "yes_no"},
                          {"id": "address", "field": "address", "rule": "in_area", "cities": ["denver"]},
                          {"id": "timeline_months", "field": "timeline_months", "rule": "max_number", "max": 6}],
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


def _rule(q, rid):
    return next(r for r in q["rules"] if r["id"] == rid)


def _rules(q, fn):
    fn(q["rules"])


# (file, mutation, expected field in message)
CASES = {
    "unknown_key": ("calendar", lambda c: c.update(bogus=1), "bogus"),
    "missing_field": ("qualification", lambda q: q.pop("rules"), "rules"),
    "unknown_rule_type": ("qualification", lambda q: _rule(q, "timeline_months").update(rule="between"), "rules"),
    "wrong_field_for_rule": ("qualification", lambda q: _rule(q, "is_owner").update(field="address"), "rules"),
    "duplicate_rule_id": ("qualification", lambda q: _rule(q, "is_owner").update(id="address"), "rules"),
    "duplicate_field": ("qualification", lambda q: q["rules"].append(
        {"id": "service2", "field": "service_type", "rule": "in_list", "values": ["repair"]}), "rules"),
    "empty_rules": ("qualification", lambda q: q.update(rules=[]), "rules"),
    "rule_question_key": ("qualification", lambda q: _rule(q, "is_owner").update(question="x"), "rules"),
    "rule_typo_key": ("qualification", lambda q: _rule(q, "address").update(citys=["x"]), "rules"),
    "negative_max": ("qualification", lambda q: _rule(q, "timeline_months").update(max=-1), "rules"),
    "in_list_not_in_synonyms": ("qualification", lambda q: _rule(q, "service_type").update(values=["replacement"]), "rules"),
    "ask_missing_rule_key": ("messages", lambda m: m["ask"].pop("address"), "ask"),
    "ask_unmatched_key": ("messages", lambda m: m["ask"].update(extra="x?"), "ask"),
    "bad_regex": ("escalation", lambda e: e.update(safety="(unclosed"), "safety"),
    "bad_tz": ("calendar", lambda c: c.update(timezone="Mars/Base"), "timezone"),
    "hours_not_increasing": ("calendar", lambda c: c.update(slot_hours=[11, 9]), "slot_hours"),
    "hours_out_of_range": ("calendar", lambda c: c.update(slot_hours=[9, 25]), "slot_hours"),
    "template_unknown_field": ("messages", lambda m: m.update(booked="Booked {whenn}."), "booked"),
    "template_positional": ("messages", lambda m: m.update(nurture="hi {}"), "nurture"),
    "template_stray_brace": ("messages", lambda m: m.update(nurture="hi {"), "nurture"),
    "ask_missing_key": ("messages", lambda m: m["ask"].pop("name"), "ask"),
    "closed_missing_key": ("messages", lambda m: m["closed"].pop("DONE"), "closed"),
    "service_area_not_lower": ("qualification", lambda q: _rule(q, "address").update(cities=["Denver"]), "rules"),
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


def test_required_false_loads(biz):
    write_pack(biz, _mut("qualification", lambda q: _rule(q, "timeline_months").update(required=False)))
    r = _rule_by_id(load_pack(SLUG).qualification, "timeline_months")
    assert r.required is False


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
import ast, re, shutil  # noqa: E402
from pathlib import Path  # noqa: E402

from . import agent, faq, policy, tools  # noqa: E402
from .tests_data import frozen_old as F  # noqa: E402


def _rule_by_id(q, rid):
    return next(r for r in q.rules if r.id == rid)


def _check(p, o):
    q = p.qualification
    cities = _rule_by_id(q, "address").cities
    assert set(cities) == set(o["area"]) and len(cities) == len(o["area"])
    assert set(_rule_by_id(q, "service_type").values) == set(o["qual"])
    assert _rule_by_id(q, "timeline_months").max == o["months"]
    assert q.owner_yes_pattern == o["yes"] and q.owner_no_pattern == o["no"] and q.non_business_pattern == o["nonbiz"]
    assert dict(q.service_synonyms) == o["service"]
    assert list(q.service_synonyms) and list(q.service_synonyms) == list(o["service"])
    assert p.escalation.safety == o["escalation"]["safety"]
    m = p.messages
    assert m.ask == o["ask"] and m.safe_fallback == o["fallback"]
    if "closed" in o:  # live constants were deleted in 03-03; only the frozen oracle checks these
        assert m.closed == o["closed"] and m.disqualify == o["disq"] and m.nurture == o["nurture"] and m.no_slots == o["noslots"]
    assert tuple((e.source, e.text) for e in p.faq) == tuple(o["faq"])
    if "hours" in o:
        assert tuple(p.calendar.slot_hours) == tuple(o["hours"]) and p.calendar.days_ahead == o["days"]
    assert q.extra_stopwords | (set(o["generic"]) - {"roof", "roofing", "summit"}) == set(o["generic"])
    assert set(q.extra_stopwords) == {"roof", "roofing", "summit"}


def _frozen():
    return dict(area=F.FROZEN_SERVICE_AREA, qual=F.FROZEN_QUALIFYING_SERVICES, months=F.FROZEN_MAX_TIMELINE_MONTHS,
                yes=F.FROZEN_OWN_YES, no=F.FROZEN_OWN_NO, nonbiz=F.FROZEN_NON_ROOF, service=F.FROZEN_SERVICE,
                escalation=F.FROZEN_ESCALATION, ask=F.FROZEN_ASK, fallback=F.FROZEN_SAFE_FALLBACK,
                closed=F.FROZEN_CLOSED_REPLY, disq=F.FROZEN_DISQUALIFY_REPLY, nurture=F.FROZEN_NURTURE_REPLY,
                noslots=F.FROZEN_NO_SLOTS_REPLY, faq=F.FROZEN_FAQ, hours=F.FROZEN_SLOT_HOURS,
                days=F.FROZEN_SLOT_DAYS_AHEAD, generic=F.FROZEN_GENERIC)


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


# ---- messages and calendar from the pack (plan 03-03) ----
# Expected strings are literals copied from the pre-extraction f-strings; never derive them from pack values.

def test_messages_booked_and_offer(roofing_pack):
    m = roofing_pack.messages
    assert m.booked.format(when="Wed Nov 04, 09:00 AM") == "You're booked for Wed Nov 04, 09:00 AM. We'll see you then!"
    opts = "; ".join(f"{i}) {w}" for i, w in enumerate(["Wed Nov 04, 09:00 AM", "Wed Nov 04, 11:00 AM"], 1))
    assert m.offer_slots.format(prefix=m.qualified_prefix, options=opts) == (
        "Good news, you qualify for a free roof inspection! Here are the next openings: "
        "1) Wed Nov 04, 09:00 AM; 2) Wed Nov 04, 11:00 AM. Which one works for you?")
    assert m.offer_slots.format(prefix=m.slot_unavailable_prefix, options="1) X").startswith("Sorry, that time isn't available. Here are")


def test_messages_owner_alert(roofing_pack):
    m = roofing_pack.messages
    kw = dict(name="Ann", when="W", phone="-", email="-", address="1 Main, Denver", need="repair")
    assert m.owner_alert_subject.format(**kw) == "New booking: Ann (W)"
    assert m.owner_alert_body.format(**kw) == ("Ann booked a free roof inspection for W.\nPhone: -\nEmail: -\n"
                                               "Address: 1 Main, Denver\nNeed: repair")


def test_messages_customer_email(roofing_pack):
    from . import agent
    m = roofing_pack.messages
    assert m.customer_subject.format(when="W") == "Your inspection is booked: W"
    body = (m.customer_intro.format(name="Ann", when="W") + agent.DEMO_NOTICE.format(business=roofing_pack.meta.business))
    assert body == ("Hi Ann,\n\nYour free roof inspection is booked for W.\n\n"
                    "This was a demo of RoofDesk AI with a sample company (Summit Roofing). No one will visit, "
                    "and nothing was scheduled.\n\nTo try RoofDesk AI for your own business, reply to this email.\n\n")


def test_messages_followup(roofing_pack):
    m = roofing_pack.messages
    kw = dict(greeting="Hi Ann,", business=roofing_pack.meta.business)
    assert m.followup_subject.format(**kw) == "Your free roof inspection with Summit Roofing"
    assert m.followup_body.format(**kw) == (
        "Hi Ann,\n\nThanks for your interest in a free roof inspection. Whenever you're ready, "
        "just reply to this email or message us and we'll find a time that works.\n\nSummit Roofing")


def test_messages_brace_in_customer_name_is_a_value(roofing_pack, monkeypatch):
    from . import agent
    sent = []
    monkeypatch.setattr(agent.mailer, "send", lambda to, s, b: sent.append((to, s, b)))
    monkeypatch.setattr(agent, "_row", lambda *a, **k: dict(name="{evil} {0}", phone=None, email="a@b.co", address="x", service_type="repair"))
    agent._notify_booking(1, "W", settings.default_tenant_id, roofing_pack)
    assert any("{evil} {0}" in b for _, _, b in sent)


def test_closed_states():
    from . import agent
    assert set(agent.CLOSED_STATES) == {"DONE", "DISQUALIFY", "ESCALATE"}


def test_fmt_roofing(roofing_pack):
    from . import agent
    assert agent._fmt("2026-11-04T09:00:00+00:00", roofing_pack) == "Wed Nov 04, 09:00 AM"
    assert agent._fmt("2026-11-06T16:00:00+00:00", roofing_pack) == "Fri Nov 06, 04:00 PM"


FROZEN_NOWS = ["2026-11-02T10:00:00+00:00", "2026-11-06T10:00:00+00:00", "2026-11-07T10:00:00+00:00",
               "2026-11-08T10:00:00+00:00", "2026-10-31T12:00:00+00:00", "2026-12-31T12:00:00+00:00",
               "2026-11-03T23:59:00+00:00", "2026-11-04T00:00:00+00:00"]
OLD_SLOT_SELECT = (
    "SELECT d + make_interval(hours => h) AS s, d + make_interval(hours => h + 1) AS e "
    "FROM generate_series(date_trunc('day', CAST(:now AS timestamptz)) + interval '1 day', "
    "date_trunc('day', CAST(:now AS timestamptz)) + make_interval(days => :n), interval '1 day') d, unnest(:hours) h "
    "WHERE extract(isodow FROM d) < 6")


@pytest.mark.parametrize("now", FROZEN_NOWS)
def test_slots_equivalence(roofing_pack, now):
    from datetime import datetime
    from .tools import slot_instants
    with db.system() as c:
        c.execute(text("SET LOCAL TimeZone='UTC'"))
        old = [(r.s, r.e) for r in c.execute(text(OLD_SLOT_SELECT), {"now": now, "n": 14, "hours": [9, 11, 14, 16]})]
    assert old and sorted(old) == sorted(slot_instants(roofing_pack.calendar, datetime.fromisoformat(now)))


def _cal(**kw):
    from .pack import Calendar
    base = dict(timezone="Etc/UTC", slot_hours=(9, 11, 14, 16), slot_minutes=60, days_ahead=14, weekdays_only=True, buffer_minutes=0)
    return Calendar(**{**base, **kw})


@pytest.mark.parametrize("kw", [dict(slot_hours=(9, 11)), dict(slot_minutes=30), dict(days_ahead=7),
                                dict(weekdays_only=False), dict(timezone="America/Denver"), dict(slot_minutes=150, buffer_minutes=0)])
def test_slots_pack_edits(kw):
    from datetime import datetime, timezone
    from .tools import slot_instants
    now = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    assert slot_instants(_cal(**kw), now) != slot_instants(_cal(), now)


def test_slots_timezone_shift():
    from datetime import datetime, timezone
    from .tools import slot_instants
    now = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    a = slot_instants(_cal(), now)[0][0]
    b = slot_instants(_cal(timezone="America/Denver"), now)[0][0]
    assert (b - a).total_seconds() == 7 * 3600  # MST on 2026-11-03


def test_slots_buffer_drops_starts():
    from datetime import datetime, timezone
    from .tools import slot_instants
    now = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    # 9-10, gaps 1h/3h/1h: buffer 120 drops 11 and 16, keeps 14
    got = {s.hour for s, _ in slot_instants(_cal(buffer_minutes=120, days_ahead=1), now)}
    assert got == {9, 14}


def test_ensure_slots_live():
    from datetime import datetime
    tid = "00000000-0000-0000-0000-0000000000c4"
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES "
                       "(:t, 'test-slots', 'S', 'UTC', 'summit-roofing') ON CONFLICT (id) DO UPDATE SET pack_slug = EXCLUDED.pack_slug"), {"t": tid})
    from .tools import ensure_slots, slot_instants
    ensure_slots(tid)
    with db.system() as c:
        n1 = c.execute(text("SELECT count(*) FROM slots WHERE tenant_id=:t"), {"t": tid}).scalar()
        seq1 = c.execute(text("SELECT last_value FROM slots_id_seq")).scalar()
    ensure_slots(tid)
    with db.system() as c:
        n2 = c.execute(text("SELECT count(*) FROM slots WHERE tenant_id=:t"), {"t": tid}).scalar()
        seq2 = c.execute(text("SELECT last_value FROM slots_id_seq")).scalar()
        other = c.execute(text("SELECT count(*) FROM slots WHERE tenant_id=:t"), {"t": settings.default_tenant_id}).scalar()
        now = c.execute(text("SELECT now()")).scalar()
        have = sorted(r.start_time for r in c.execute(text("SELECT start_time FROM slots WHERE tenant_id=:t"), {"t": tid}))
    assert n1 == n2 > 0 and seq1 == seq2 and other >= 0
    want = sorted(s for s, _ in slot_instants(get_pack(tid).calendar, datetime.now(now.tzinfo)))
    assert [h for h in have if h >= want[0]][:len(want)] == want


# ---- policy equivalence (plan 03-04) ----
def _old_escalation(message, only=None):
    for reason, pattern in F.FROZEN_ESCALATION.items():
        if (only is None or reason in only) and re.search(pattern, message, re.I):
            return reason
    return None


ESC_SAMPLES = ["Can I talk to a real person?", "I'm calling my lawyer", "part of my roof collapsed",
               "This is ridiculous, you're useless", "I rent my place in Denver", "gas smell in the attic",
               "this is ridiculous, part of my roof collapsed", "I will sue you and it is a scam",
               "speak to a manager, there is a gas leak", "my wires are exposed wires, furious", "hello there",
               "I will take this to court, worst service"]


@pytest.mark.parametrize("msg", ESC_SAMPLES)
@pytest.mark.parametrize("only", [None, ("safety", "legal")])
def test_escalation_equivalence(roofing_pack, msg, only):
    assert policy.escalation_reason(msg, only=only, pack=roofing_pack) == _old_escalation(msg, only)


def test_escalation_mixed_safety_angry_is_safety(roofing_pack):
    assert policy.escalation_reason("this is ridiculous, part of my roof collapsed", pack=roofing_pack) == "safety"


def test_escalation_without_pack_has_no_safety():
    assert policy.escalation_reason("gas leak and a collapsed ceiling") is None
    assert policy.escalation_reason("I will sue you") == "legal"
    assert policy.escalation_reason("this is ridiculous, part of my roof collapsed") == "angry"


def _old_grounded(field, value, message, asked=""):
    msg = message.lower()
    if field == "is_owner":
        if value:
            return bool(re.search(F.FROZEN_OWN_YES, msg)) and not re.search(F.FROZEN_OWN_NO, msg)
        answered_no = "own" in asked.lower() and re.match(r"\W*(no|nope|nah)\b", msg)
        return bool(re.search(F.FROZEN_OWN_NO, msg) or answered_no)
    if field == "service_type":
        return bool(re.search(F.FROZEN_NON_ROOF if value == "other" else F.FROZEN_SERVICE[value], msg))
    return None


GRID_MSGS = ["my roof has a leak", "I own the house", "I rent", "yes", "no", "please fix my gutter", "new roof please",
             "can you inspect it", "solar panels", "just the roof", "I'm a tenant", "I don't own it", "hello"]


@pytest.mark.parametrize("msg", GRID_MSGS)
def test_grounding_equivalence(roofing_pack, msg):
    for value in ("repair", "replacement", "inspection", "other"):
        assert policy.is_grounded(roofing_pack, "service_type", value, msg) == _old_grounded("service_type", value, msg)
    for value in (True, False):
        for asked in ("", "Do you own the property?"):
            assert policy.is_grounded(roofing_pack, "is_owner", value, msg, asked) == _old_grounded("is_owner", value, msg, asked)


def _old_supported(answer, faq_texts):
    vocab = policy._tokens(" ".join(faq_texts)) | F.FROZEN_GENERIC
    words = re.findall(r"[a-z]{4,}", answer.lower())
    return not words or sum(not policy._same_word(w, vocab) for w in words) / len(words) <= 0.4


@pytest.mark.parametrize("answer", ["The roof is free", "Summit Roofing serves Denver", "We are licensed and insured roofing",
                                    "It takes about 45 minutes", "Thanks, happy to help with the roof inspection"])
def test_answer_supported_equivalence(roofing_pack, answer):
    faq = ["The inspection takes about 45 to 60 minutes."]
    assert policy.answer_supported(answer, faq, roofing_pack) == _old_supported(answer, faq)


def test_answer_supported_without_pack_keeps_core_stopwords_only():
    assert policy.answer_supported("roof roof roof roof", ["nothing here"]) is False  # roof is a pack stopword


# ---- cache: tenants never share packs (T-03-14) ----
def test_cache_interleaved_tenants_and_reload(tmp_path, monkeypatch):
    from .pack import _CACHE
    biz = tmp_path
    real = settings.businesses_dir / "summit-roofing"
    monkeypatch.setattr(settings, "businesses_dir", tmp_path)
    other = "00000000-0000-0000-0000-0000000000c2"
    shutil.copytree(real, biz / "summit-roofing")
    write_pack(biz)
    with db.system() as c:
        c.execute(text("INSERT INTO tenants (id, slug, name, timezone, pack_slug) VALUES (:t, 'test-cache', 'C', 'UTC', :p) "
                       "ON CONFLICT (id) DO UPDATE SET pack_slug = :p"), {"t": other, "p": SLUG})
    a1, b1 = get_pack(), get_pack(other)
    a2, b2 = get_pack(), get_pack(other)
    assert (a1.slug, b1.slug) == ("summit-roofing", SLUG) and a1 is a2 and b1 is b2
    path = biz / SLUG / "messages.yaml"
    data = yaml.safe_load(path.read_text())
    data["safe_fallback"] = "changed fallback"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    b3 = get_pack(other)
    assert b3.hash != b1.hash and b3.messages.safe_fallback == "changed fallback"
    assert len([k for k in _CACHE if k[0] == other]) == 1
    assert get_pack().slug == "summit-roofing"


# ---- no business globals in core modules (PACK-07) ----
CORE = ("policy.py", "agent.py", "tools.py", "faq.py", "admin.py")
OLD_NAMES = {"SERVICE_AREA", "QUALIFYING_SERVICES", "MAX_TIMELINE_MONTHS", "SAFE_FALLBACK", "ASK", "_OWN_YES", "_OWN_NO",
             "_SERVICE", "_NON_ROOF", "FAQ", "SLOT_HOURS", "SLOT_DAYS_AHEAD"}


@pytest.mark.parametrize("name", CORE)
def test_no_globals(name):
    src = (Path(__file__).parent / name).read_text()
    assert not re.findall(r"summit|roof(?!desk)|denver", src, re.I)
    assigned = {t.id for n in ast.parse(src).body if isinstance(n, (ast.Assign, ast.AnnAssign))
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    assert not assigned & OLD_NAMES
