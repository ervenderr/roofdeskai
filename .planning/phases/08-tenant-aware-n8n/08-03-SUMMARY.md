---
phase: 08-tenant-aware-n8n
plan: 03
subsystem: ci-and-auth
tags: [n8n, ci-check, admin-auth]
requirements: [WF-01, WF-05]
key-files:
  created: [api/app/test_n8n_workflows.py]
  modified: [Makefile, docker-compose.yml, api/app/admin.py, api/app/test_admin.py, api/app/test_routes_scope.py]
completed: 2026-11-04
---

# Phase 8 Plan 03: CI check and admin hard 400 Summary

`make check-n8n` statically guards every n8n workflow (tenant key header, no literal keys, no Code-node HTTP, catalog), and admin-key writes without a tenant now return 400.

## Commits
- d1879df test: ci check for tenant key header on n8n workflows
- f44484c fix: require explicit tenant on admin write routes

## What changed
- `check_workflow(name, data, raw)` in `test_n8n_workflows.py` (pure, used by real-file tests and 18 mutant tests). Rules: API nodes in tenant-aware workflows need `X-API-Key` starting with `=` containing `JSON.parse($env.TENANT_API_KEYS)`; `X-Admin-Key` only on `GET .../admin/tenants`; no `X-Tenant-Id`; no credential auth; no Code-node HTTP or key-into-item; scheduled tenant-aware workflows need `saveDataSuccessExecution: none`; untenanted workflows need `X-Admin-Key`; error-handler has no API node; id == basename; errorWorkflow set; no `rd_live_`; catalog set; daily-report absent; compose keeps `N8N_BLOCK_ENV_ACCESS_IN_NODE "false"`; `.env.example` has no `rd_live_` (files must exist, asserted not skipped).
- `docker-compose.yml`: api mounts `./n8n:/srv/n8n:ro`, `./docker-compose.yml:/srv/docker-compose.yml:ro`, `./.env.example:/srv/.env.example:ro` (api recreated on the branch project only). `Makefile`: `check-n8n`.
- `admin._write_tenant` raises 400 `tenant required: send X-API-Key, or X-Admin-Key with X-Tenant-Id` (no default-tenant fallback, warning removed). Read routes unchanged.
- Tests: `test_admin.py` shared header `H` now carries `X-Tenant-Id`; new test asserts admin-only on the three write routes gives 400 and row counts for leads/conversations/messages/escalations unchanged. `test_routes_scope.py` fallback test replaced by a 400 plus zero-new-conversations assertion.

## Verification (real output)
- RED (checker stubbed to return []): `18 failed, 8 passed` (all 18 mutants missed). GREEN: `make check-n8n` -> `26 passed in 0.08s`. No workflow was changed to satisfy the checker.
- RED for admin: `FAILED test_admin_without_tenant_is_400_and_writes_nothing`, `FAILED test_inbound_admin_without_header_is_400`. GREEN: admin/routes_scope/keys/tenancy/isolation -> `97 passed`; `make check-n8n` -> `26 passed`.
- Full `make g-test` (run alone): `1089 passed, 1 warning`. `git status --short businesses prompts` empty.
- `grep -rln X-Admin-Key n8n/workflows`: only followup-scheduler (the /admin/tenants node) and outreach-flow.

## Deviations
- [Rule 1 - scope] The saveDataSuccessExecution rule applies to tenant-aware scheduled workflows only. `outreach-flow` (allowlisted, untenanted, plan says no change) has Schedule Triggers without it, so applying the rule there would force editing it.
- Also mounted `docker-compose.yml` and `.env.example` into api (as the plan requires) so those two assertions run.

## Not verified / notes
- GitHub Actions wiring is out of scope (no workflows dir); `make check-n8n` is the CI entry point.
- No live n8n or mail run in this plan (static and API tests only). `log`/`logging` in admin.py is now unused (left in place).
- Plans 4 and 5 must extend `EXPECTED` in the test.

## Self-Check: PASSED
Commits d1879df and f44484c exist; test file present.
