---
phase: 06-per-tenant-keys-and-rls-enforcement
plan: 06
requirements: [SEC-04, SEC-03, SEC-05]
key-files:
  created: [api/app/test_leak.py]
  modified: [evals/reports/latest.md]
metrics:
  tasks: 2
  completed: 2026-11-04
---

# Phase 6 Plan 06: Leak test and regression gates Summary

Cross-tenant leak test (11 test functions, 27 cases) passes on the RLS-enabled DB; roofing gate is 94/96 with the same two failures and dental is 43/43, both local-model only with no regressions.

Commits: 87cac2b (test_leak.py), a879ae7 (roofing report).

## Results (real output)

- Leak test: `app/test_leak.py` 27 passed. Covers: own-rows-only on /leads, /conversations, /admin/escalations, /admin/followups/due (both tenants, cross-id 404); /metrics tenant vs admin; chat creds (body tenant_id and X-Tenant-Id ignored, cross-tenant continuation 404, no key / wrong / rotated-out / revoked = 401); tenant key on admin-only routes 401/403; lookup_faq, get_available_slots, book_appointment(slot of other tenant) raises ToolError; app_rw with no tenant context sees 0 rows on all 11 tables; INSERT without context raises "row-level security"; `assert_rls_enforced()`. Catalog checks (FORCE, no defaults, app_rw role shape) stay in `test_rls_proof.py`.
- First leak-test run failed on a bug in the test itself (missing NOT NULL `source` in my faq_chunks seed insert); fixed in the test. No production leak found.
- Full pytest: `615 passed, 1 warning` before the gates and again after (18s), never concurrent with an eval.
- Roofing gate (`--pack summit-roofing --gate`, GIT_SHA 87cac2b, LLM_TIMEOUT_S=300): EXIT=0, `94/96`, Models `local:llama3.1:8b`, failures exactly `voice-over-explainer` and `voice-indecisive`, `regressions: []`, `flaky-pass: []`, GATE PASSED. escalation recall 11/11, booking validity 100%, schema validity 95% over 232 calls, p50/p95 7.6s/9.6s.
- Dental gate (`--pack bright-smile-dental --gate`): EXIT=0, `43/43`, Models `local:llama3.1:8b`, `regressions: []`, GATE PASSED. escalation recall 9/9 (precision 9/10), booking validity 100%.
- `git diff evals/baselines/v1-roofing.json` empty; no --write-baseline.
- Plan 01 failing node id (intermittent post-eval failure): `app/test_agent.py::test_slots_are_topped_up_when_the_calendar_runs_short` (test_agent.py:155, cross-tenant slot duplicate query); fixed in 06-01, and no recurrence after both evals in this run.

## ROADMAP Phase 6 criteria evidence

1. Hashed per-tenant keys issue/rotate/revoke, shown once: test_keys.py + leak test rotate/revoke 401.
2. Tenant derived from credential, never body; no key = 401: leak test body/header ignored, no-key 401.
3. RLS FORCE, non-owner app role, defaults dropped: test_rls_proof.py catalog tests, `assert_rls_enforced`, 0 rows without context on 11 tables.
4. Cross-tenant leak test on RLS DB: test_leak.py 27 passed.
5. Admin scope separate from tenant keys: tenant key 401/403 on admin routes; admin key cross-tenant.
Plus gates: roofing 94/96 same two failures, dental 43/43.

## Deviations and deploy notes

- **D-06 deviation:** `settings.default_tenant_id` survives in admin.py (admin-key calls without X-Tenant-Id fall back to it with a logged warning, until Phase 8 when n8n sends tenant keys) and in triage.py (RoofDesk own-funnel pack lookup, D-08), plus config/tests.
- **D-10 mechanism:** second engine. `engine` (DATABASE_URL, superuser owner) is the system engine; `app_engine` (APP_DATABASE_URL, role `app_rw`) backs `tx()`. No BYPASSRLS role.
- **D-05 keyless /chat:** only via `PUBLIC_DEMO_TENANT_ID` (unset on the branch). Deploy action: set `PUBLIC_DEMO_TENANT_ID=00000000-0000-0000-0000-000000000001` or roofdeskai.com /chat returns 401.
- **Deploy env:** set `APP_DB_PASSWORD` and `APP_DATABASE_URL`. API will not boot without APP_DATABASE_URL (startup guard `assert_rls_enforced`).
- **Hosted DB:** if the migrator/owner role is not a superuser, run `ALTER ROLE <owner> BYPASSRLS` once (FORCE RLS would otherwise hide all rows from the system engine); a non-superuser owner also needs `app_rw` pre-created.
- Dental eval run also modified tracked `evals/reports/bright-smile-dental.md`; left uncommitted (plan commits only latest.md). Untracked partial reports, `.planning/config.json`, scripts/check-and-deploy.sh, docs/media untouched.
- Carry-over still open: confirm "call 144" emergency number with the user.

## Not verified

- n8n flows and the live roofdeskai.com deployment were not exercised; no push/deploy done.
