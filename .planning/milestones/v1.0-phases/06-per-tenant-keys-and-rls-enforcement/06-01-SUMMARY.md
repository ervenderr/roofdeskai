---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 01
requirements: [SEC-04]
key-files:
  modified: [api/app/test_agent.py, api/app/conftest.py]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 01: Stabilise pytest after evals Summary

Slot-dupes assertion now groups by `tenant_id, start_time`, and conftest cleanup deletes only rows of `test-%` tenants (agent_events by tenant, tenant_api_keys guarded by `to_regclass`).

## Task 1: flake reproduced

- Stack up via `make g-up`; DB role is superuser (`rolsuper = t`).
- Baseline `make g-test`: `497 passed, 1 warning in 7.42s`.
- After seeding bright-smile-dental slots (`ensure_tenant` + `tools.ensure_slots`):
  `make g-test ARGS="app/test_agent.py -q -x -p no:cacheprovider"` failed with
  `FAILED app/test_agent.py::test_slots_are_topped_up_when_the_calendar_runs_short` (`app/test_agent.py:155: AssertionError`). Matches research A1.
- Side effect observed: that run's old blanket cleanup wiped the dental tenant's slots (T-06-01 confirmed real).

## Task 2: fix (commit 4ef2257)

- `make g-test` run twice after the fix:
  - `497 passed, 1 warning in 6.57s`
  - `497 passed, 1 warning in 6.06s`
- Re-seeded dental and ran twice more: `497 passed ... in 5.90s`, `497 passed ... in 5.97s`. Dental slots: 90 before, 27 between and after (never 0).

## Deviations / not verified

- Dental slot count drops 90 -> 27 on the first run because `test_slots_are_topped_up...` itself deletes unbooked slots > 3 days for all tenants (pre-existing test behaviour, not conftest) and only tops up the default tenant. Rows survive; left alone as out of scope.
- The `tenant_api_keys` cleanup branch is untested until plan 02 creates the table (guard path only exercised).
- Evals not run (not required by this plan).
- Pre-existing `conversations/prospects/campaigns` id-range cleanup in conftest left as is.
