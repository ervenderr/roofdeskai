---
phase: 13-capacity-daily-brief-and-isolation
plan: 01
subsystem: api
tags: [daily-brief, isolation, rls, tdd]
requires: [12-03]
provides: [GET /daily-brief, two-tenant isolation test]
affects: [api/app/brief_routes.py]
key-files:
  created: [api/app/test_owner_isolation.py]
  modified: [api/app/brief_routes.py, api/app/test_brief.py]
requirements: [BRF-01, ISO-01]
completed: 2026-11-05
---

# Phase 13 Plan 01: GET /daily-brief and isolation test Summary

`GET /daily-brief` (tenant key, connectors module, `tx(tenant)` plus explicit `tenant_id` filter, `LIMIT 14`) returns `{latest, runs}`; a two-tenant Python test proves drafts, capacity flags and briefs are owner-only.

## Commits
- 3bfa3ac test: failing tests for GET /daily-brief (RED)
- 496c0e9 feat: GET /daily-brief latest brief and recent runs (GREEN; also adjusts the 405 test, see deviations)
- 0ecd77c test: two-tenant isolation over drafts, capacity flags and brief

## Verification
- RED: `make g-test ARGS="app/test_brief.py"` -> `6 failed, 12 passed`. All six new tests failed; GET /daily-brief answered 404 Not Found (e.g. `test_get_brief_empty: AssertionError {"detail":"N...`).
- GREEN: `app/test_brief.py` -> `18 passed`.
- `app/test_owner_isolation.py` -> `1 passed`.
- Full `make g-test` -> `1284 passed, 1 warning`, exit 0.
- `python3 -m scripts.check_shared` -> `check-shared OK: 11 allowlisted files, no other hits`.
- `INSERT INTO drafts` count in the isolation test: 0 (seeded via POST /quotes, /capacity/check, /daily-brief).
- `git diff` of brief_routes.py shows only the docstring line and the added GET handler; `daily_brief`, `_due_for`, `due` untouched.
- Isolation test is new coverage on top of Task 1 code, so it had no separate RED (Task 1 was already in).

## Deviations from Plan
- **[Rule 1 - plan assumption]** Plan says `GET /daily-brief/due` is 405. In this app the `/` StaticFiles mount answers every unmatched GET, so it is 404 both before and after (same for `GET /capacity/check`). The test asserts `in (404, 405)` with a comment; POST /due is still asserted 200. No code change.
- Commit messages carry the Co-Authored-By line per the caller's instruction.

## Known Stubs
None.

## Self-Check: PASSED
