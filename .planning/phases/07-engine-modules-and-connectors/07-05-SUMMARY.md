---
phase: 07-engine-modules-and-connectors
plan: 05
subsystem: connectors-brief
tags: [connectors, mock, daily-brief, due, dst]
requires: [07-04]
provides: [Connectors pack model + Pack.connectors, engine.connectors (4 mock adapters), engine.brief (build_brief, find_disagreements, is_due), POST /daily-brief, POST /daily-brief/due, capacity bookings-connector fallback]
key-files:
  created: [api/app/engine/connectors.py, api/app/engine/brief.py, api/app/brief_routes.py, api/app/test_connectors.py, api/app/test_brief.py, api/app/tests_data/packs/demo-venue/connectors.yaml]
  modified: [api/app/pack.py, api/app/capacity_routes.py, api/app/main.py, api/app/test_pack_modules.py, api/app/test_capacity_api.py]
requirements-completed: [MOD-04, MOD-05]
metrics: {tasks: 2, commits: [1a7b886]}
---

# Phase 7 Plan 05: Connectors and daily brief Summary

Deterministic mock connectors (sha256-seeded, labelled "(mock data)") and a one-page tenant-local daily brief, idempotent per local date via `brief_runs`, with `/daily-brief/due` (BRIEF_GRACE_HOURS=3) and a bookings-connector fallback for `/capacity/check`.

## Commit
- 1a7b886 `feat: mock connectors and tenant-local daily brief` (both tasks in one commit)

## Verification (real output)
- Targeted: `make g-test ARGS="app/test_connectors.py app/test_brief.py app/test_pack_modules.py app/test_capacity_api.py -q"` -> all dots, no failures.
- Full `make g-test`: `830 passed, 1 warning in 17.36s`.
- After run: tenants are `summit-roofing`, `bright-smile-dental`; `count(*) from brief_runs` = 0 (no demo-venue / test-venue2 rows left; conftest needed no change).

## Coverage highlights
- Two subprocesses with different PYTHONHASHSEED give identical metrics; a different slug differs. Every result `source == "mock"`; every non-failed section carries "(mock data)"; failed `ads` shows "ads: source unavailable" and is never a disagreement; adapter exception text never appears (type name only).
- Disagreement shape `bookings_count: bookings=14 vs sheet=17 (diff 3, tolerance 1)`; abs and pct tolerance; within tolerance no flag.
- `is_due` rows: Zurich 06:59 no, 07:00 yes, 09:59 yes, 10:00 no, ran no; spring-forward 2026-03-29 send_hour 2 (01:59 no, 03:00 yes); fall-back 2026-10-25 (second 02:30 blocked by already_ran).
- Routes: create + idempotent replay (no recompute), force recompute, roofing 404, admin-only 401, tenant key self-only / empty when not due / empty after run, admin iterates two tenants (roofing skipped, no connectors), admin + X-Tenant-Id acts as tenant, tenant B sees no runs of A.
- Capacity: connector used when body has no bookings; explicit empty connector list is checkable (under_utilised flags); unavailable connector -> `source_unavailable`, no flags resolved; without connector and body -> 422 as before.
- Roofing/dental: pinned hash test green; `.connectors is None` asserted for both.

## Decisions
- Sheet mock reports the same underlying booking count as bookings, so a disagreement only arises from `mock.offsets`.
- `/daily-brief/due` with no credential returns 403 (existing `require_scope`/`require_admin` behaviour), invalid tenant key 401.
- Connector-unavailable capacity response is HTTP 200 with `source_unavailable: "bookings"`.
- Money is formatted with `pack.services.currency` when present, otherwise bare 2dp.

## Deviations from Plan
- Process: implementation was written before the tests (not strictly tests-first); no RED run was recorded. Tests were then written and some failed and were fixed (Decimal accepted in Metric validator; 403 vs 401 expectation; subprocess env).
- `api/app/config.py` not modified: BRIEF_GRACE_HOURS lives in `engine/brief.py` as a named constant.
- Existing `test_no_bookings_is_422_and_leaves_flags` now deletes the demo-venue `connectors.yaml` in the tmp pack (the fixture now has a bookings connector).

## Not verified / risks
- Eval (94/96, 43/43) not run: no roofing/dental files touched; gate is end of phase.
- Concurrent `/daily-brief` calls not tested under real concurrency (ON CONFLICT path reasoned, not exercised).
- Capacity fallback fetches one connector call per day in range (<= 60), fine for mocks, revisit for real adapters.

## Self-Check: PASSED
Files exist; commit 1a7b886 present.
