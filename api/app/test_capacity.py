"""MOD-03: pure capacity checker. Real zoneinfo (no mocks) for the DST cases."""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from .engine.capacity import Booking, Override, check_capacity, classify, window_utc
from .pack import Capacity, Shift, load_pack

UTC = timezone.utc
DEN, ZUR = ZoneInfo("America/Denver"), ZoneInfo("Europe/Zurich")
FIXTURES = Path(__file__).parent / "tests_data" / "packs"


def shift(**kw):
    base = dict(id="s", days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"], start="00:00", end="23:59",
                min_staff=1, max_covers_per_staff=10, staff=1)
    return {**base, **kw}


def cap(*shifts, horizon_days=14):
    return Capacity.model_validate({"shifts": [shift(**s) for s in shifts], "horizon_days": horizon_days})


def bk(iso, covers=1):
    return Booking(start=datetime.fromisoformat(iso), covers=covers)


def z(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def run(c, tz, bookings, first, last=None, overrides=()):
    return check_capacity(c, tz, bookings, first, last or first, overrides)


# --- window math: the four DST days ---------------------------------------------------------------------------
@pytest.mark.parametrize("tz,d,start,end,hours", [
    (DEN, date(2026, 3, 8), "2026-03-08T07:00:00Z", "2026-03-08T12:00:00Z", 5),
    (DEN, date(2026, 11, 1), "2026-11-01T06:00:00Z", "2026-11-01T13:00:00Z", 7),
    (ZUR, date(2026, 3, 29), "2026-03-28T23:00:00Z", "2026-03-29T04:00:00Z", 5),
    (ZUR, date(2026, 10, 25), "2026-10-24T22:00:00Z", "2026-10-25T05:00:00Z", 7),
])
def test_midnight_shift_window_on_dst_days(tz, d, start, end, hours):
    s, e = window_utc(d, time(0, 0), time(6, 0), tz)
    assert (s, e) == (z(start), z(end))
    assert e - s == timedelta(hours=hours)


def test_zurich_01_to_04_spans_two_real_hours():
    s, e = window_utc(date(2026, 3, 29), time(1, 0), time(4, 0), ZUR)
    assert e - s == timedelta(hours=2)


def test_shift_starting_in_the_gap_resolves_with_fold_0():
    s, e = window_utc(date(2026, 3, 29), time(2, 30), time(4, 0), ZUR)
    assert s == z("2026-03-29T01:30:00Z") and e == z("2026-03-29T02:00:00Z")


def test_fall_back_bookings_at_0730z_and_0830z_are_both_counted():
    c = cap(dict(id="sunday_night", days=["sun"], end="06:00"))
    one = run(c, DEN, [bk("2026-11-01T07:30:00Z", 6)], date(2026, 11, 1))
    two = run(c, DEN, [bk("2026-11-01T07:30:00Z", 6), bk("2026-11-01T08:30:00Z", 6)], date(2026, 11, 1))
    assert [f.kind for f in one] == []
    assert [(f.kind, f.covers, f.capacity) for f in two] == [("over_capacity", 12, 10)]
    assert [f.flag_key for f in two] == ["over_capacity:sunday_night:2026-11-01"]  # one key on the 25h day


def test_spring_forward_booking_belongs_to_its_local_date():
    c = cap(dict(max_covers_per_staff=1))
    flags = run(c, DEN, [bk("2026-03-08T06:30:00Z", 2), bk("2026-03-08T09:30:00Z", 2)], date(2026, 3, 7), date(2026, 3, 8))
    # 06:30Z = 23:30 MST on Mar 7; 09:30Z = 03:30 MDT on Mar 8
    assert sorted((f.shift_date.isoformat(), f.covers) for f in flags) == [("2026-03-07", 2), ("2026-03-08", 2)]


def test_instant_near_utc_midnight_lands_on_local_date():
    c = cap(dict(max_covers_per_staff=1))
    flags = run(c, ZUR, [bk("2026-07-01T22:30:00Z", 2)], date(2026, 7, 1), date(2026, 7, 2))
    assert [f.shift_date.isoformat() for f in flags] == ["2026-07-02"]  # 00:30 CEST


def test_window_end_is_exclusive():
    c = cap(dict(id="a", end="06:00", max_covers_per_staff=1))
    assert run(c, ZUR, [bk("2026-07-01T04:00:00Z", 2)], date(2026, 7, 1)) == []  # 06:00 CEST: outside
    assert len(run(c, ZUR, [bk("2026-07-01T03:59:00Z", 2)], date(2026, 7, 1))) == 1


# --- flag kinds and boundaries ----------------------------------------------------------------------------------
D = date(2026, 7, 1)  # a Wednesday
AT = "2026-07-01T10:00:00Z"  # 12:00 Zurich


def kinds(flags):
    return sorted(f.kind for f in flags)


def test_over_capacity_boundary_equal_is_fine():
    c = cap(dict(staff=2, min_staff=2))
    assert kinds(run(c, ZUR, [bk(AT, 20)], D)) == []
    assert kinds(run(c, ZUR, [bk(AT, 21)], D)) == ["over_capacity"]


def test_hard_max_covers_caps_below_staff_math():
    c = cap(dict(staff=3, min_staff=1, max_covers=25))
    flags = run(c, ZUR, [bk(AT, 26)], D)
    assert [(f.kind, f.capacity) for f in flags] == [("over_capacity", 25)]


def test_understaffed_needs_bookings():
    c = cap(dict(staff=1, min_staff=2))
    assert kinds(run(c, ZUR, [], D)) == []
    assert kinds(run(c, ZUR, [bk(AT, 1)], D)) == ["understaffed"]


def test_under_utilised_threshold():
    c = cap(dict(staff=3, min_staff=2))
    assert kinds(run(c, ZUR, [], D)) == ["under_utilised"]
    assert kinds(run(c, ZUR, [bk(AT, 25)], D)) == []  # ceil(25/10) = 3 staff needed
    assert kinds(run(c, ZUR, [bk(AT, 20)], D)) == ["under_utilised"]  # 2 would do


def test_multiple_flags_on_one_shift():
    c = cap(dict(staff=1, min_staff=2))
    flags = run(c, ZUR, [bk(AT, 15)], D)
    assert kinds(flags) == ["over_capacity", "understaffed"]
    assert len({f.flag_key for f in flags}) == 2


def test_staff_override_replaces_default():
    c = cap(dict(id="s", staff=1, min_staff=2))
    assert kinds(run(c, ZUR, [bk(AT, 1)], D)) == ["understaffed"]
    ov = [Override(shift_id="s", date=D, staff=2)]
    assert kinds(run(c, ZUR, [bk(AT, 1)], D, overrides=ov)) == []
    ov_other_day = [Override(shift_id="s", date=D + timedelta(days=1), staff=2)]
    assert kinds(run(c, ZUR, [bk(AT, 1)], D, overrides=ov_other_day)) == ["understaffed"]


def test_days_filter_and_flag_key():
    c = cap(dict(id="sunday_night", days=["sun"], end="06:00"))
    assert run(c, ZUR, [], date(2026, 7, 1)) == []  # Wednesday
    f = run(c, ZUR, [], date(2026, 7, 5))  # Sunday, staff 1, min 1, no bookings: nothing
    assert f == []
    f = run(cap(dict(id="x", staff=3, min_staff=1)), ZUR, [], D)
    assert f[0].flag_key == "under_utilised:x:2026-07-01"


def test_hash_stable_and_sensitive_to_a_moved_booking():
    c = cap(dict(staff=1, max_covers_per_staff=1))
    a = run(c, ZUR, [bk(AT, 2)], D)[0].input_hash
    assert run(c, ZUR, [bk(AT, 2)], D)[0].input_hash == a
    assert run(c, ZUR, [bk("2026-07-01T11:00:00Z", 2)], D)[0].input_hash != a  # same covers, moved
    assert run(c, ZUR, [bk(AT, 3)], D)[0].input_hash != a
    both = [bk("2026-07-01T11:00:00Z", 1), bk(AT, 1)]
    assert run(c, ZUR, both, D)[0].input_hash == run(c, ZUR, both[::-1], D)[0].input_hash  # order-independent


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        Booking(start=datetime(2026, 7, 1, 12, 0), covers=1)
    with pytest.raises(ValidationError):
        Booking(start=z(AT), covers=0)
    with pytest.raises(ValidationError):
        Booking(start=z(AT), covers=1001)


# --- classify -------------------------------------------------------------------------------------------------
def test_classify_new_unchanged_reflagged_resolved():
    c = cap(dict(id="s", staff=1, max_covers_per_staff=1))
    f1 = run(c, ZUR, [bk(AT, 2)], D)
    key = f1[0].flag_key
    r = classify({}, f1, D, D)
    assert r == {"new": [key], "unchanged": [], "reflagged": [], "resolved": []}
    db = {key: (f1[0].input_hash, False)}
    assert classify(db, f1, D, D)["unchanged"] == [key]
    f2 = run(c, ZUR, [bk(AT, 3)], D)
    assert classify(db, f2, D, D)["reflagged"] == [key]
    assert classify(db, [], D, D) == {"new": [], "unchanged": [], "reflagged": [], "resolved": [key]}
    # a resolved flag that comes back is re-flagged, even with the same hash
    assert classify({key: (f1[0].input_hash, True)}, f1, D, D)["reflagged"] == [key]
    # an already-resolved flag is not resolved again
    assert classify({key: (f1[0].input_hash, True)}, [], D, D)["resolved"] == []


def test_classify_never_resolves_outside_the_checked_range():
    db = {"over_capacity:s:2026-07-20": ("h", False), "over_capacity:s:2026-06-30": ("h", False),
          "over_capacity:s:2026-07-01": ("h", False)}
    assert classify(db, [], D, date(2026, 7, 7))["resolved"] == ["over_capacity:s:2026-07-01"]


# --- pack model --------------------------------------------------------------------------------------------------
def test_fixture_pack_capacity_loads():
    p = load_pack("demo-venue", base=FIXTURES)
    assert [s.id for s in p.capacity.shifts] == ["weekday_evening", "weekend_day", "sunday_night"]
    assert p.capacity.horizon_days == 14 and p.capacity.shifts[1].max_covers == 30


@pytest.mark.parametrize("bad", [
    dict(start="17:00", end="17:00"), dict(start="18:00", end="17:00"), dict(start=1020),
    dict(days=["funday"]), dict(days=[]), dict(staff=-1), dict(max_covers_per_staff=0), dict(typo=1),
])
def test_bad_shift_rejected(bad):
    with pytest.raises(ValidationError):
        Shift.model_validate(shift(**bad))


def test_duplicate_shift_ids_rejected():
    with pytest.raises(ValidationError):
        Capacity.model_validate({"shifts": [shift(id="a"), shift(id="a")]})
