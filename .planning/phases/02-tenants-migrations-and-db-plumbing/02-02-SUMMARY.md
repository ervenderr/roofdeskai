---
phase: 02-tenants-migrations-and-db-plumbing
plan: 02
subsystem: database
tags: [migrations, tenancy, postgres]
requires: [02-01]
provides: [tenant_id columns, composite keys, agent_events]
key-files:
  created: [db/migrations/002_tenant_columns.sql, db/migrations/003_tenant_keys.sql, db/migrations/004_agent_events.sql]
  modified: [api/app/conftest.py, api/app/test_tenancy.py, api/app/test_migrations.py]
requirements-completed: [TEN-02, TEN-05, TEN-06]
completed: 2026-11-03
---

# Phase 2 Plan 02: Tenant columns, composite keys, agent_events Summary

Migrations 002 (tenant_id NOT NULL DEFAULT Summit on 9 tables; llm_calls nullable with no default, backfilled from conversations), 003 (duplicate-slot pre-check first, composite uniques and composite FKs), 004 (append-only agent_events with UPDATE/DELETE/TRUNCATE triggers).

- Commits: b91e2eb (002, 003 and tests), see git log for 004 and conftest cleanup.
- RED run: 10 failed / 12 passed before migrations; after 002/003 only the agent_events test failed; after 004 green.
- `make g-test` full suite: 235 passed. After the suite: tenants count 1, agent_events count 0, no scratch_ databases left.
- Migrations applied to the branch stack DB via `python -m app.bootstrap` (duplicate-slot pre-check passed there). Live DB untouched.

## Deviations from Plan

- The `%` rule: used `quote_ident` concatenation instead of `format()` in 003 because the runner uses exec_driver_sql (psycopg treats `%`).
- All dropped FKs were plain NO ACTION; the composite replacements are the same.

## Known Stubs
None.

## Self-Check: PASSED
