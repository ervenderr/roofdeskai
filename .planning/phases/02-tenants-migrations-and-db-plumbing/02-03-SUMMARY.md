---
phase: 02-tenants-migrations-and-db-plumbing
plan: 03
subsystem: database
tags: [tenancy, tools, faq, agent_events]
requires: [02-02]
provides: [tenant-aware tools and faq, db.record_event, per-tenant FAQ seeding]
key-files:
  modified: [api/app/tools.py, api/app/faq.py, api/app/main.py, api/app/db.py, api/app/test_tenancy.py]
requirements-completed: [TEN-03, TEN-04, TEN-05]
completed: 2026-11-03
---

# Phase 2 Plan 03: Tenant-aware tools, FAQ and agent_events Summary

tools.py and faq.py have no raw engine usage; every tool takes a trailing `tenant_id` keyword, filters and stamps by tenant; `tools.run` writes tool_calls and an `agent_events` row (name/ok/ms only); escalations write kind `escalation` (reason only). Startup seeds FAQ for every tenant.

- Commits: f88fe3c (Task 1), 9bd2420 (Task 2).
- RED run: 9 failed / 13 passed in `-k tenancy` before implementation.
- `make g-test` full suite: 244 passed. No scratch_ databases left.

## Decisions
- `run(..., tenant_id=None)` is a parameter of its own; it strips any `tenant_id` from model args and passes it to the tool only when set, so existing `(query, k=3)` test lambdas keep working until plan 04.
- `seed_faq(tenant_id, reload=False)`: reload deletes only that tenant's rows then reinserts.
- Event writes go through `_safe_event` (own transaction, `log.exception`, never blocks the tool).

## Deviations from Plan
None. Tests ran on the branch dev DB with a `test-b3` tenant (removed by conftest session cleanup), not scratch DBs. Eval subset gate not run (full gate is plan 05).

## Known Stubs
None.

## Self-Check: PASSED
