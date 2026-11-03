"""MOD-07: intake_event normaliser/merge (pure) and POST /intake_event (idempotent upsert)."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, db
from .config import settings
from .engine.intake import MISSING, FieldError, apply_event, get_path, normalise_event
from .main import app
from .pack import EventMap, Intake, load_pack

FIXTURES = Path(__file__).parent / "tests_data" / "packs"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def imap():
    return load_pack("demo-venue", base=FIXTURES).meta.intake


def W(**kw):
    return {"guest": {"email": "Guest@X.com", "name": "Gina", **kw}, "signed_at": "2026-11-01T10:00:00Z"}


def test_get_path():
    assert get_path({"a": {"b": 1}}, "a.b") == 1
    assert get_path({"a": {"b": 1}}, "a.c") is MISSING
    assert get_path({"a": 5}, "a.b") is MISSING
    assert get_path({"a": [1]}, "a.b") is MISSING


def test_waiver_normalises(imap):
    e = normalise_event(imap.waiver, "waiver", W(), now=NOW)
    assert e.person_key == "guest@x.com" and e.name == "Gina" and e.occurred_at == datetime(2026, 11, 1, 10, tzinfo=timezone.utc)


def test_case_different_emails_same_person(imap):
    a = normalise_event(imap.waiver, "waiver", W(), now=NOW)
    b = normalise_event(imap.checkin, "checkin", {"guest": {"email": " guest@x.COM "}}, now=NOW)
    assert a.person_key == b.person_key


def test_phone_formatting_and_first_non_empty(imap):
    p = {"guest": {"email": "", "phone": "+41 (79) 123-45.67"}}
    assert normalise_event(imap.checkin, "checkin", p, now=NOW).person_key == "+41791234567"
    assert normalise_event(imap.checkin, "checkin", {"guest": {"phone": "079 123 45 67"}}, now=NOW).person_key == "0791234567"


def test_int_key_ok_and_occurred_at_fallback(imap):
    e = normalise_event(imap.checkin, "checkin", {"guest": {"phone": 4155550100}, "arrived_at": "2026-11-01T10:00:00"}, now=NOW)
    assert e.person_key == "4155550100" and e.occurred_at == NOW  # naive timestamp is not trusted


@pytest.mark.parametrize("bad", [{"a": 1}, [1], True, 1.5, "x" * 201, "   "])
def test_bad_person_key_rejected(imap, bad):
    r = normalise_event(imap.checkin, "checkin", {"guest": {"email": bad}}, now=NOW)
    assert isinstance(r, list) and r[0].field == "person_key" and r[0].event == "checkin"
    assert r[0].tried == ("guest.email", "guest.phone")
    assert "x" * 20 not in repr(r)


def test_missing_key_error_shape(imap):
    r = normalise_event(imap.waiver, "waiver", {}, now=NOW)
    assert r == [FieldError("waiver", "person_key", ("guest.email", "guest.phone"), "missing")]


def test_name_too_long(imap):
    r = normalise_event(imap.waiver, "waiver", W(name="n" * 201), now=NOW)
    assert r[0].field == "name" and "nnnn" not in repr(r)


def test_result_fields(imap):
    p = {"guest": {"email": "a@b.co", "name": "A"}, "game": {"score": 7, "time": 3000.5}, "team": {"name": "Reds"}, "finished_at": "2026-11-01T11:00:00+00:00"}
    e = normalise_event(imap.result, "result", p, now=NOW)
    assert e.fields == {"score": 7, "team": "Reds", "time_seconds": 3000.5}
    assert normalise_event(imap.result, "result", {**p, "team": {"name": {"x": 1}}}, now=NOW)[0].field == "fields.team"
    r = normalise_event(imap.result, "result", {**p, "team": {"name": "s" * 501}}, now=NOW)
    assert r[0].field == "fields.team" and "sssss" not in repr(r)
    assert normalise_event(imap.result, "result", {**p, "game": {}}, now=NOW).fields == {"team": "Reds"}


def test_apply_event_idempotent_and_merge(imap):
    w = normalise_event(imap.waiver, "waiver", W(), now=NOW)
    p1 = apply_event(None, w)
    assert apply_event(p1, w) == p1
    later = normalise_event(imap.waiver, "waiver", {**W(), "signed_at": "2026-11-03T10:00:00Z"}, now=NOW)
    assert apply_event(p1, later)["waiver_at"] == p1["waiver_at"]  # earliest wins
    c = normalise_event(imap.checkin, "checkin", {"guest": {"email": "guest@x.com"}, "arrived_at": "2026-11-04T09:00:00Z"}, now=NOW)
    p2 = apply_event(p1, c)
    assert p2["waiver_at"] and p2["checkin_at"] and p2["name"] == "Gina"
    assert p1["checkin_at"] is None  # input not mutated


def test_apply_event_result_out_of_order(imap):
    def res(score, at):
        return normalise_event(imap.result, "result", {"guest": {"email": "a@b.co"}, "game": {"score": score}, "finished_at": at}, now=NOW)
    new, old = res(9, "2026-11-02T10:00:00Z"), res(3, "2026-11-01T10:00:00Z")
    p = apply_event(apply_event(None, new), old)
    assert p["result"] == {"score": 9}
    assert apply_event(p, new) == p
    assert apply_event(apply_event(None, old), new)["result"] == {"score": 9}


def test_intake_model_rules():
    with pytest.raises(ValueError):
        Intake()
    with pytest.raises(ValueError):
        Intake(waiver=EventMap(person_key=("a",), fields={"x": "b"}))
    with pytest.raises(ValueError):
        EventMap(person_key=("a[0]",))
    with pytest.raises(ValueError):
        EventMap(person_key=("a", "b", "c", "d"))
    with pytest.raises(ValueError):
        EventMap(person_key=("a",), bogus=1)


def test_shipped_packs_have_no_intake_block():
    for slug in ("summit-roofing", "bright-smile-dental"):
        assert load_pack(slug).meta.intake is None


# ---- POST /intake_event ----
PII = ["Gina Ghost", "ghost@secret.example", "+41790001122"]


@pytest.fixture
def client():
    return TestClient(app)


def _wipe(*tenants):
    with db.system() as c:
        for t in tenants:
            c.execute(text("DELETE FROM intake_people WHERE tenant_id = :t"), {"t": t})


@pytest.fixture
def h(venue_tenant):
    _wipe(venue_tenant)
    yield {"X-API-Key": auth.issue_key(venue_tenant)["key"]}
    _wipe(venue_tenant)


def post(client, h, event, payload):
    return client.post("/intake_event", json={"event": event, "payload": payload}, headers=h)


def rows(t):
    with db.tx(t) as c:
        return [dict(r) for r in c.execute(text("SELECT * FROM intake_people ORDER BY id")).mappings()]


WAIVER = {"guest": {"email": "Ghost@Secret.example", "name": "Gina Ghost"}, "signed_at": "2026-11-01T10:00:00Z"}


def test_waiver_twice_one_row(client, h, venue_tenant):
    a = post(client, h, "waiver", WAIVER)
    b = post(client, h, "waiver", WAIVER)
    assert a.status_code == b.status_code == 200, a.text
    assert a.json()["created"] is True and b.json()["created"] is False and a.json()["person_id"] == b.json()["person_id"]
    assert len(rows(venue_tenant)) == 1


def test_waiver_then_checkin_same_person(client, h, venue_tenant):
    post(client, h, "waiver", WAIVER)
    r = post(client, h, "checkin", {"guest": {"email": "ghost@secret.EXAMPLE"}, "arrived_at": "2026-11-04T09:00:00Z"})
    assert r.json()["created"] is False
    (row,) = rows(venue_tenant)
    assert row["waiver_at"] and row["checkin_at"] and row["name"] == "Gina Ghost"


def test_replayed_waiver_keeps_earliest(client, h, venue_tenant):
    post(client, h, "waiver", WAIVER)
    post(client, h, "waiver", {**WAIVER, "signed_at": "2026-11-03T10:00:00Z"})
    assert rows(venue_tenant)[0]["waiver_at"].isoformat().startswith("2026-11-01T10:00")


def test_result_newer_replaces_older_does_not_regress(client, h, venue_tenant):
    def res(score, at):
        return post(client, h, "result", {"guest": {"email": "ghost@secret.example"}, "game": {"score": score}, "finished_at": at})
    res(5, "2026-11-02T10:00:00Z")
    res(9, "2026-11-03T10:00:00Z")
    assert rows(venue_tenant)[0]["result"] == {"score": 9}
    res(1, "2026-11-01T10:00:00Z")
    res(9, "2026-11-03T10:00:00Z")
    (row,) = rows(venue_tenant)
    assert row["result"] == {"score": 9}


@pytest.mark.parametrize("body", [
    {"event": "nope", "payload": {}}, {"event": "waiver"}, {"event": "waiver", "payload": "x"}, {"event": "waiver", "payload": {}, "extra": 1}])
def test_bad_body_422(client, h, body):
    assert client.post("/intake_event", json=body, headers=h).status_code == 422


def test_missing_key_422_names_field_without_values(client, h, venue_tenant):
    r = post(client, h, "waiver", {"guest": {"name": "Gina Ghost"}})
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert d["event"] == "waiver" and d["field"] == "person_key" and d["tried"] == ["guest.email", "guest.phone"]
    assert "Gina" not in r.text and rows(venue_tenant) == []


def test_wrong_type_422_no_echo(client, h):
    r = post(client, h, "waiver", {"guest": {"email": {"a": "ghost@secret.example"}}})
    assert r.status_code == 422 and "secret" not in r.text


def test_oversized_payload_422(client, h):
    r = post(client, h, "waiver", {**WAIVER, "junk": "j" * 33000})
    assert r.status_code == 422 and "jjjj" not in r.text


def test_event_not_mapped_422(client, h, venue_tenant, monkeypatch):
    from . import intake_event_routes, pack
    real = pack.get_pack(venue_tenant)
    cut = real.model_copy(update={"meta": real.meta.model_copy(update={"intake": real.meta.intake.model_copy(update={"checkin": None})})})
    monkeypatch.setattr(intake_event_routes, "get_pack", lambda t: cut)
    r = post(client, h, "checkin", {"guest": {"email": "a@b.co"}})
    assert r.status_code == 422 and r.json()["detail"][0]["msg"] == "event not mapped"


def test_no_pii_in_logs_or_events(client, h, venue_tenant, caplog):
    caplog.set_level(logging.DEBUG)
    post(client, h, "waiver", WAIVER)
    post(client, h, "waiver", {"guest": {"name": "Gina Ghost"}})
    for p in PII:
        assert p.lower() not in caplog.text.lower()
    with db.tx(venue_tenant) as c:
        ev = json.dumps([dict(r) for r in c.execute(text("SELECT payload FROM agent_events WHERE kind='intake_event'")).mappings()])
    assert '"person_id"' in ev and '"waiver"' in ev
    for p in PII:
        assert p.lower() not in ev.lower()


def test_roofing_is_404(client, roofing_tenant):
    hh = {"X-API-Key": auth.issue_key(roofing_tenant)["key"]}
    r = post(client, hh, "waiver", WAIVER)
    assert r.status_code == 404 and r.json()["detail"] == "module not enabled"


def test_admin_key_alone_401(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "adm")
    assert post(client, {"X-Admin-Key": "adm"}, "waiver", WAIVER).status_code == 401


def test_rls_and_per_tenant_rows(client, h, venue_tenant, roofing_tenant):
    post(client, h, "waiver", WAIVER)
    q = "INSERT INTO intake_people (tenant_id, person_key) VALUES (:t, 'ghost@secret.example')"
    try:
        with db.tx(roofing_tenant) as c:
            c.execute(text(q), {"t": roofing_tenant})
        assert len(rows(roofing_tenant)) == 1 and len(rows(venue_tenant)) == 1  # same key, two tenants, two rows
        assert rows(roofing_tenant)[0]["tenant_id"] != rows(venue_tenant)[0]["tenant_id"]
    finally:
        _wipe(roofing_tenant)
