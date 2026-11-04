---
phase: 08-tenant-aware-n8n
verified: 2026-11-04T00:00:00Z
status: human_needed
score: 4/5 success criteria verified, 1 partial (SC5 wiring into CI)
human_verification:
  - test: "Decide whether `make check-n8n` (31 pytest cases) satisfies 'CI fails' for SC5/WF-05, given the repo has no .github/workflows"
    expected: "Either accept the make target as the gate (add an override) or schedule a CI runner (Phase 9 mentions CI drift checks)"
    why_human: "Scope decision; the checker itself is verified"
  - test: "Decide on the 'Check key' abort behaviour (see Findings)"
    expected: "Accept as a deploy precondition or change the node to skip unkeyed tenants"
    why_human: "Product/ops tradeoff"
---

# Phase 8: Tenant-Aware n8n Verification Report

**Goal:** All workflows run per tenant, and the platform still works with n8n off.
**Mode:** read-only code audit (no pytest, evals or Docker run by the verifier). SUMMARY gate numbers (1103 passed, 31 n8n, 94/96) were NOT re-run.
**Known/accepted:** ROADMAP "6 existing / 11 workflows" is superseded by 3 tenant-keyed + 2 allowlisted untenanted + 5 new = 10 files. Confirmed: n8n/workflows holds exactly those 10 JSONs.

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Existing workflows send tenant key header and take owner address from API | VERIFIED | Parsed all workflow JSON. inbound-message (`Call agent` -> /webhooks/inbound), followup-scheduler, escalation-alert all send `X-API-Key`. Owner address comes from `GET /tenant/me` (`Tenant me` / `Require owner` nodes in escalation-alert, inbound-message `Build alert`). `/tenant/me` returns `owner_email` (tenant_routes.py:20, tenants.py:31). outreach-flow and error-handler are untenanted by design: outreach uses `X-Admin-Key` on every API node, error-handler calls no API (both enforced by the test). |
| 2 | quote-request, review-reply, capacity-check, daily-brief, intake-event run end to end | VERIFIED (partly via SUMMARY) | All five files present with webhook/schedule, normalize, API call (`/quotes`, `/reviews/draft`, `/capacity/check`, `/daily-brief`, `/intake_event`), respond and owner/customer mail nodes wired in connections. API routes exist (brief_routes.py, intake_event_routes.py, quotes.py, drafts.py). E2E evidence is in 08-06-SUMMARY only (escalation mail, intake 200/422, capacity 3 flags + mail, sender lanes, nightly). Not re-run. Not exercised per SUMMARY: quote/review webhook lanes, inbound booking-confirmation lane, daily-brief due-and-sent through n8n (the latter covered by test_run_flows). |
| 3 | Scheduled workflow loops `GET /admin/tenants`, acts only on due tenants in local time | VERIFIED | daily-brief: Hourly -> `List tenants` (/admin/tenants, X-Admin-Key) -> `Each tenant` (splitInBatches) -> Check key -> Tenant me -> Gate (connectors module + owner_email) -> `Due` (`POST /daily-brief/due`) -> `Is due` -> Brief -> Send -> Loop end -> back to loop. The API decides due-ness (`/daily-brief/due`, brief_routes.py:81), not n8n. Same loop shape in followup-scheduler, capacity-check nightly, quote-request and review-reply senders. Admin key is allowed only on the tenant-list node (enforced by checker). |
| 4 | With n8n stopped, same flows complete via API | VERIFIED | scripts/run_flows.py implements followups, daily_brief, capacity_nightly, send_approved plus inbound/escalation_alert helpers against the same endpoints, mail via app.mailer; `make run-flows` target exists; test_run_flows.py exists. Admin key used only for `/admin/tenants`. SUMMARY reports an n8n-stopped live run (send_approved: 1 sent, mail delivered). Not re-run here. |
| 5 | CI fails when an API-calling n8n HTTP node lacks the tenant key header | PARTIAL (WARNING) | Checker is real and strict (test_n8n_workflows.py `check_workflow`): per-HTTP-node API detection, tenant-key header must be `=`-expression over `JSON.parse($env.TENANT_API_KEYS)`, no literal keys/`rd_live_`, no X-Tenant-Id, no credentials auth, code-node HTTP bypass blocked, plus ~17 mutant tests proving it bites, and a parametrised run over every real file. `make check-n8n` exists (Makefile:29). BUT there is no CI runner: `.github/workflows` does not exist, and 08-06-SUMMARY lists "GitHub Actions wiring deferred". So nothing fails automatically on push; it fails only when someone runs the make target/test suite. Note test_compose_and_env_example reads `/srv/docker-compose.yml`, so it only passes inside the api container. |

Requirements: WF-01 satisfied, WF-02 satisfied (E2E per SUMMARY), WF-03 satisfied, WF-04 satisfied, WF-05 satisfied at checker level, pending CI wiring (see SC5). REQUIREMENTS.md still shows all five Pending and ROADMAP still unchecked/stale wording; orchestrator is to amend.

## Findings

### `Check key` aborts the tenant loop (WARNING, not a blocker)
Code in every scheduled workflow: `if (!keys[id]) throw new Error('no key for tenant ' + id)`. Confirmed in daily-brief.json; the same node is in followup-scheduler, capacity-check, quote-request and review-reply. The throw fails the whole execution, so any tenant after the unkeyed one in `/admin/tenants` order is skipped, and the error-handler fires. Severity: low to medium. It is fail-loud (not silent, no cross-tenant data leak, no wrong-key use), and the SC's goal (per-tenant operation) holds when keys are provisioned. The cost is blast radius: one new tenant created without a key (e.g. via a future `make new-business` in Phase 9) stalls the briefs, follow-ups and sends of all later tenants until fixed. It also contradicts run_flows.py, which skips unkeyed tenants, so n8n-on and n8n-off behave differently. Recommended fix before Phase 9 onboarding is used: route the missing-key case to `Loop end` (an IF node or return an empty item with a skip flag) while still alerting, or make `make new-business` mint the key and update `TENANT_API_KEYS` as a hard step. Interim: treat "every tenant has a key" as a documented deploy precondition (already noted in SUMMARY).

### Other notes (info)
- Webhook trust is internal-port only; shared secret deferred (per SUMMARY).
- Stale `daily-report` may linger on the existing n8n volume; the test asserts the file is gone from the repo.
- Debt-marker scan not performed beyond the files read; none seen in the audited files.

## Gaps
No FAILED truths. One WARNING (SC5 has no CI runner) and one WARNING (Check key abort). Status human_needed because both need a decision; neither blocks the phase goal functionally.

_Verifier: Claude (gsd-verifier), read-only audit_
