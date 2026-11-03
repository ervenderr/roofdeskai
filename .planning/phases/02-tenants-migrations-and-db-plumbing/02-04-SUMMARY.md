---
phase: 02-tenants-migrations-and-db-plumbing
plan: 04
subsystem: database
tags: [tenancy, agent, logging, evals]
requires: [02-03]
provides: [tenant-aware handle_turn, tenant-stamped logs, turn_start events]
key-files:
  created: [api/app/logctx.py, api/app/test_logging_tenant.py]
  modified: [api/app/agent.py, api/app/main.py, api/app/admin.py, evals/runner.py, scripts/seed_demo.py, api/app/test_agent.py, api/app/test_tenancy.py]
requirements-completed: [TEN-03, TEN-05, TEN-06]
completed: 2026-11-03
---

# Phase 2 Plan 04: Tenant through the agent, admin, evals and logs Summary

`handle_turn(..., tenant_id=)` threads one tenant to every DB helper, tool and llm_calls row; `_open`/`token_matches` filter by tenant; a `turn_start` agent_event is written per turn; log lines carry `tenant=<id>` (`-` outside a turn).

- Commits: 9f134c6 (agent/main/admin/evals/seed + tests), 6064ffd (logging).
- RED run: 3 failed in `test_tenancy.py -k 'turn or other_tenants'` and a collection error for `test_logging_tenant.py` before implementation.
- `make g-test`: 252 passed.

## Decisions
- No `functools.partial`: 02-03 made `tools.run(..., tenant_id=)` its own parameter that strips any model-supplied tenant, so agent.py just passes `tenant_id=t`. Test lambdas in test_agent.py now accept `tenant_id=None` anyway.
- `_exec(sql, tenant, **params)`, `_set_state(..., *, t)`; `conversation_token`/`token_matches` take optional `tenant_id` (default tenant), so `/chat` stays on Summit.
- `admin._rows(sql, *, _tenant=None, **params)`: None = system, else tenant tx. Cross-tenant lists stay system.
- Outreach, pilot, scrapes, prospects left untouched (untenanted). Outreach llm_calls keep NULL tenant (DB check prints 0).
- Log PII audit: all log calls log ids, field names or exception names only; grep hits were static messages containing the word "email".

## Deviations from Plan
- Plan acceptance grep for `partial` in agent.py does not match, by instruction (see above).
- Eval subset gate not run (full gate is plan 05). evals/runner.py imports cleanly in the container.

## Known Stubs
None.

## Self-Check: PASSED
