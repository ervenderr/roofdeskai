---
phase: 07-engine-modules-and-connectors
plan: 04
subsystem: capacity
tags: [capacity, dst, zoneinfo, flags, dedupe]
requires: [07-02, 07-03]
provides: [Capacity/Shift pack model + Pack.capacity, engine.capacity (window_utc, check_capacity, classify), POST /capacity/check, GET /capacity/flags]
affects: [07-05 (bookings connector feeds the body), 07-08 (capacity evals)]
key-files:
  created: [api/app/engine/capacity.py, api/app/capacity_routes.py, api/app/test_capacity.py, api/app/test_capacity_api.py, api/app/tests_data/packs/demo-venue/capacity.yaml]
  modified: [api/app/pack.py, api/app/main.py, api/app/test_pack_modules.py]
requirements-completed: [MOD-03]
metrics: {tasks: 2, commits: [ab9fca5, 7a0c516]}
---

# Phase 7 Plan 04: Capacity checker Summary

Pure, integer-math capacity checker over `capacity.yaml` shifts with DST-safe UTC windows, persisted as deduplicated flags (new / unchanged / reflagged / resolved) behind `POST /capacity/check`.

## Commits
- ab9fca5 `feat: capacity pack model and pure DST-safe checker`
- 7a0c516 `feat: capacity checker with dedupe, re-flag and DST-safe windows`

## Verification (real output)
- RED: `app/test_capacity.py` -> collection error (no `app.engine.capacity`).
- Task 1: `make g-test ARGS="app/test_capacity.py app/test_pack_modules.py -q"` -> `.........................................................  [100%]`.
- Task 2: `app/test_capacity_api.py` -> 16 tests, all pass after fixing one test-side mistake (a Jul 8 run legitimately adds its own under_utilised row).
- Full `make g-test`: `797 passed, 1 warning in 17.07s`.
- After the run: tenants are `bright-smile-dental`, `summit-roofing`; `count(*) from capacity_flags` = 0 (no demo-venue row left).

## Coverage highlights
- Windows with real zoneinfo: Denver 2026-03-08 (5h), 2026-11-01 (7h), Zurich 2026-03-29 (5h), 2026-10-25 (7h), exact UTC instants; fall-back bookings 07:30Z and 08:30Z counted separately with a single flag key; spring-forward local-date assignment; 02:30 gap start -> fold=0 (01:30Z); Zurich 01:00-04:00 = 2h; UTC-midnight bookings land on the local date; window end exclusive.
- Flags: each kind, boundary equal-to-capacity, hard `max_covers`, overrides, several flags per shift, hash stable / order-independent / sensitive to a moved booking.
- HTTP: new -> unchanged (rows identical) -> reflagged (`reflagged_at` set) -> resolved (row kept, `resolved_at` set) -> recurs: status `reflagged`, `resolved_at` back to NULL, still one row; a later-week run does not resolve earlier flags; no bookings (missing or empty) -> 422 "no booking source" with flags untouched; naive datetime 422; bad override shift / unordered / over-horizon range 422; RLS leak (other tenant sees 0 rows); roofing 404 `module not enabled`; admin key alone 401.
- Roofing/dental: pinned hash test green, `.capacity is None` asserted for both.

## Decisions
- `classify(existing, computed, first, last)` takes `flag_key -> (hash, is_resolved)`; the shift date for range checks is parsed from the key (shift ids cannot contain `:`).
- Persistence: lock existing rows in the date range (`SELECT ... FOR UPDATE`), classify purely, then INSERT ... ON CONFLICT DO NOTHING for new, UPDATE for reflagged/resolved. (Plan said insert-then-select per flag; this is equivalent and uses the pure classifier.)
- Empty `bookings: []` is treated like missing (422), per the plan; a genuinely empty day cannot be checked until the bookings connector exists.
- Default range: today in tenant tz through `horizon_days`; explicit range must span at most `horizon_days`.
- `capacity_checked` event payload holds only dates and flag keys.

## Deviations from Plan
None. No conftest change needed (07-02 cleanup already covers `capacity_flags` and demo-venue events).

## Not verified / risks
- Eval (94/96, 43/43) not run: no roofing/dental pack or prompt files touched; gate is end of phase.
- Concurrent first-time inserts of the same key: loser's `DO NOTHING` is silent, so both runs may report `new` (not tested under real concurrency).
- Overnight shifts unsupported (`shortcut:` comment in `pack.py`); appointments-table source omitted (`shortcut:` in `capacity_routes.py`).

## Self-Check: PASSED
Files exist, commits ab9fca5 and 7a0c516 present.
