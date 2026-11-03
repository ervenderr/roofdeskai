"""MOD-03: POST /capacity/check, GET /capacity/flags (tenant key, capacity module, dedupe/re-flag/resolve)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from . import auth, db
from .config import settings
from .main import app

# demo-venue is Europe/Zurich; Wed 2026-07-01 hits only weekday_evening (17:00-23:00 local = 15:00Z-21:00Z, staff 3, cap 30)
DAY = "2026-07-01"
BOOK = "2026-07-01T16:00:00Z"
KEY = f"over_capacity:weekday_evening:{DAY}"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def h(venue_tenant):
    def wipe():
        with db.system() as c:
            c.execute(text("DELETE FROM capacity_flags WHERE tenant_id = :t"), {"t": venue_tenant})
    wipe()
    yield {"X-API-Key": auth.issue_key(venue_tenant)["key"]}
    wipe()


def check(client, h, covers, first=DAY, last=DAY, **extra):
    body = {"bookings": [{"start": BOOK, "covers": covers}], "first": first, "last": last, **extra}
    return client.post("/capacity/check", json=body, headers=h)


def rows(tenant):
    with db.tx(tenant) as c:
        return c.execute(text("SELECT flag_key, first_flagged_at, reflagged_at, resolved_at FROM capacity_flags ORDER BY id")).all()


def statuses(r):
    return {f["flag_key"]: f["status"] for f in r.json()["flags"]}


def test_first_run_flags_new(client, h, venue_tenant):
    r = check(client, h, 31)
    assert r.status_code == 200, r.text
    assert statuses(r) == {KEY: "new"} and r.json()["resolved"] == [] and r.json()["checked_shifts"] == 1
    f = r.json()["flags"][0]
    assert (f["kind"], f["shift_id"], f["date"], f["staff"], f["covers"], f["capacity"]) == ("over_capacity", "weekday_evening", DAY, 3, 31, 30)
    assert [x["flag_key"] for x in client.get("/capacity/flags?open=true", headers=h).json()] == [KEY]


def test_identical_rerun_creates_nothing(client, h, venue_tenant):
    check(client, h, 31)
    before = rows(venue_tenant)
    r = check(client, h, 31)
    assert statuses(r) == {KEY: "unchanged"}
    assert rows(venue_tenant) == before  # same row, same first_flagged_at, no reflagged_at


def test_changed_input_reflags(client, h, venue_tenant):
    check(client, h, 31)
    r = check(client, h, 33)
    assert statuses(r) == {KEY: "reflagged"}
    (row,) = rows(venue_tenant)
    assert row.reflagged_at is not None and row.resolved_at is None


def test_fixed_input_resolves_and_keeps_row(client, h, venue_tenant):
    check(client, h, 31)
    r = check(client, h, 25)  # ceil(25/10) = 3 staff: no flags
    assert r.json()["flags"] == [] and r.json()["resolved"] == [KEY]
    (row,) = rows(venue_tenant)
    assert row.resolved_at is not None
    assert client.get("/capacity/flags?open=true", headers=h).json() == []
    assert [x["flag_key"] for x in client.get("/capacity/flags", headers=h).json()] == [KEY]


def test_resolved_flag_that_recurs_is_reflagged_and_reopened(client, h, venue_tenant):
    check(client, h, 31)
    check(client, h, 25)
    r = check(client, h, 31)  # same inputs as the original flag
    assert statuses(r) == {KEY: "reflagged"}
    (row,) = rows(venue_tenant)
    assert row.resolved_at is None and row.reflagged_at is not None and len(rows(venue_tenant)) == 1
    assert [x["flag_key"] for x in client.get("/capacity/flags?open=true", headers=h).json()] == [KEY]


def test_run_for_a_later_week_does_not_resolve_earlier_flags(client, h, venue_tenant):
    check(client, h, 31)
    r = check(client, h, 25, first="2026-07-08", last="2026-07-08")
    assert r.status_code == 200 and r.json()["resolved"] == []
    (row,) = [x for x in rows(venue_tenant) if x.flag_key == KEY]  # the Jul 8 run itself adds an under_utilised flag
    assert row.resolved_at is None


def test_no_bookings_is_422_and_leaves_flags(client, h, venue_tenant):
    check(client, h, 31)
    before = rows(venue_tenant)
    for body in ({"first": DAY, "last": DAY}, {"bookings": [], "first": DAY, "last": DAY}):
        r = client.post("/capacity/check", json=body, headers=h)
        assert r.status_code == 422 and "no booking source" in r.text
    assert rows(venue_tenant) == before


def test_naive_datetime_is_422(client, h):
    r = client.post("/capacity/check", json={"bookings": [{"start": "2026-07-01T18:00:00", "covers": 5}]}, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize("extra", [
    {"staff_overrides": [{"shift_id": "nope", "date": DAY, "staff": 1}]},
    {"first": "2026-07-05", "last": "2026-07-01"},
    {"first": "2026-07-01", "last": "2026-08-30"},  # beyond horizon_days
])
def test_bad_range_or_override_is_422(client, h, extra):
    body = {"bookings": [{"start": BOOK, "covers": 5}], **extra}
    assert client.post("/capacity/check", json=body, headers=h).status_code == 422


def test_staff_override_changes_flags(client, h):
    ov = [{"shift_id": "weekday_evening", "date": DAY, "staff": 1}]
    r = check(client, h, 5, staff_overrides=ov)
    assert sorted(f["kind"] for f in r.json()["flags"]) == ["understaffed"]


def test_default_range_uses_horizon(client, h):
    r = client.post("/capacity/check", json={"bookings": [{"start": BOOK, "covers": 5}]}, headers=h)
    assert r.status_code == 200 and r.json()["checked_shifts"] >= 1


def test_other_tenant_cannot_see_flags(client, h, venue_tenant, roofing_tenant):
    check(client, h, 31)
    with db.tx(roofing_tenant) as c:  # RLS: the other tenant's rows are invisible
        assert c.execute(text("SELECT count(*) FROM capacity_flags")).scalar() == 0
    hh = {"X-API-Key": auth.issue_key(roofing_tenant)["key"]}
    assert client.get("/capacity/flags?open=true", headers=hh).status_code == 404


def test_roofing_tenant_module_not_enabled(client, roofing_tenant):
    hh = {"X-API-Key": auth.issue_key(roofing_tenant)["key"]}
    r = client.post("/capacity/check", json={"bookings": [{"start": BOOK, "covers": 5}]}, headers=hh)
    assert r.status_code == 404 and r.json()["detail"] == "module not enabled"


def test_admin_key_alone_is_401(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "adm")
    assert client.post("/capacity/check", json={}, headers={"X-Admin-Key": "adm"}).status_code == 401
    assert client.get("/capacity/flags", headers={"X-Admin-Key": "adm"}).status_code == 401
