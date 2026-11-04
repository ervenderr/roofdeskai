---
phase: 08-tenant-aware-n8n
plan: 06
subsystem: n8n-off-and-gates
tags: [run-flows, e2e, gates]
requirements: [WF-01, WF-02, WF-03, WF-04, WF-05]
key-files:
  created: [scripts/run_flows.py, api/app/test_run_flows.py, docker-compose.e2e.yml]
  modified: [Makefile, .gitignore, api/app/test_admin.py, evals/reports/latest.md]
completed: 2026-11-04
---

# Phase 8 Plan 06: n8n-off proof, headless E2E, phase gates Summary

`scripts/run_flows.py` (+ `make run-flows`) runs the workflow call sequences with no n8n; the module workflows were driven on the branch stack; roofing 94/96 and dental 43/43 hold.

## Commits
- efcf0b2 feat: run flows without n8n
- f658d10 test: e2e overlay for module workflow proof
- (this SUMMARY + roofing report) docs: phase 8 gate results

## Task 1 (TDD)
RED: `app/test_run_flows.py` failed at collection (`scripts.run_flows` missing). GREEN: `make g-test ARGS="app/test_run_flows.py app/test_n8n_workflows.py -q"` -> all dots, 100%. Tests: booking + customer mail; web escalation with webhook unset (one owner mail) and with a closed-port webhook; sms escalation through `inbound` -> `escalation_alert`; follow-up once then nothing; daily brief once then nothing (utcnow patched to 07:00 Zurich); mixed approved quote drafts (with/without contact_email: only the first is mailed and `sent`, the other stays `approved`); capacity nightly; recorded headers prove `X-Admin-Key` appears only on `GET /admin/tenants`. Unlike the n8n lanes, run_flows skips a tenant that has no key.

## Task 2: headless E2E (branch project roofdesk-global, overlay docker-compose.e2e.yml, gitignored .e2e-businesses with demo-venue)
Overlay also set MAIL_TRANSPORT=mailpit and OWNER_EMAIL=owner@example.test for the api (the branch api is normally configured for real SMTP). TENANT_API_KEYS only in the host shell/scratchpad; no key printed or committed; n8n execution output checked for `rd_live_`: none.
- (a) `POST /webhook/inbound-message` (roofing, contact e2e-phase8-1, "let me speak to a real person") -> 200; mailpit: `Escalation (human_request): conversation 9532 -> owner@example.test`.
- (b) `followup-scheduler` and `daily-brief` via `n8n execute --rawOutput`: status success both. daily-brief sent nothing: demo-venue was not in its send hour (the due-and-sent path is proven by test_run_flows).
- (c) `POST /webhook/intake-event` demo-venue: valid waiver -> `200 {"person_id":92,"created":true}`; invalid -> `422` with the API detail body (`field person_key, tried guest.email/guest.phone, missing`). Research A1 confirmed: no node fix needed.
- (d) capacity-check webhook with a booking of 31 covers -> `200 {"checked_shifts":3,"flags":3}` and mail `Capacity flags: 3 -> owner@example.test`. Nightly lane (execute): success, mail `Capacity flags: 14`.
- quote-request sender lane, mixed items (3 tenants: dental nothing due, demo-venue with 2 approved quotes one with and one without contact_email, roofing nothing due): status success; `Each tenant` 4 runs, `Check key`/`Tenant me`/`List approved`/`Loop end` 3 runs each, so all three tenants were reached. Mail `Your quote from Demo Venue -> customer@example.test`; draft 481 `sent`, draft 482 (no email) stays `approved`.
- review-reply sender lane: success, mail `Approved review reply #483 -> owner@example.test`, draft `sent`.
- n8n stopped, `make run-flows` (with the overlay supplying keys): `followups: 0 sent / daily_brief: 0 sent / capacity_nightly: 0 sent / send_approved: 1 sent`; mailpit `Your quote from Demo Venue -> nooff@example.test`, draft `sent`. n8n container confirmed stopped, then restarted.
- Cleanup: demo-venue tenant, its keys and rows, E2E-labeled keys, E2E conversations/leads/messages/escalations, drafts, flags, brief runs, intake people, faq/slots; slots un-booked. `GET /admin/tenants` -> 200 `['bright-smile-dental','summit-roofing']`. api/n8n recreated without overlay and without TENANT_API_KEYS: config shows MAIL_TRANSPORT smtp and the original OWNER_EMAIL again; `/srv/businesses` holds the two packs. `.e2e-businesses/` moved out of the repo. `git status --short businesses prompts evals/baselines` empty.
- admin.py unchanged: a new test (`test_tenant_list_tolerates_a_missing_pack_dir`) passed first time, since `GET /admin/tenants` reads only the tenants table.

### Not run (reason)
- Webhook lanes of quote-request and review-reply, inbound booking-confirmation lane: need the model to write text/complete a booking; not driven (covered by API tests and run_flows equivalents).
- daily-brief due-and-sent through n8n: n8n cannot be moved into a send window; only "not due, success" observed.
- CLI `n8n execute` picked each workflow's scheduled trigger (Every 15 min, Hourly, Nightly), not the Manual Trigger node; the downstream path is identical. `execute` against the running server fails on the task-broker port 5679, so each run used a one-off container with n8n stopped.
- Capacity webhook 422 path, live SMTP delivery, GitHub Actions.

### Finding for the orchestrator (not fixed, out of scope)
The `Check key` Code node in all scheduled workflows throws when a tenant has no entry in TENANT_API_KEYS. The first run failed with `no key for tenant <dental>` before dental was given a key, which aborts the whole loop, so one unkeyed tenant stops every tenant after it. Ensure every tenant has a key before deploy, or change the workflows to skip. run_flows skips unkeyed tenants.

## Task 3: gates (strictly sequential)
- `make g-test`: `1103 passed, 1 warning in 22.65s`. `make check-n8n`: `31 passed in 0.06s`.
- Roofing (llama3.1:8b warmed keep_alive 6h, slots re-seeded, LLM_TIMEOUT_S=300, override not committed): `Models: local:llama3.1:8b`, `Overall: 94/96 scenarios passed`, failures exactly `voice-over-explainer` and `voice-indecisive`, final lines `improvements: [] / new (not in baseline): [] / flaky-pass: [] / regressions: [] / GATE PASSED`.
- Dental (slots re-seeded): `Overall: 43/43 scenarios passed`, Models local:llama3.1:8b, `regressions: []`, `GATE PASSED`.
- `git status --short businesses prompts evals/baselines` empty.

## Deviations
- The overlay docker-compose.e2e.yml is committed as the plan's artifact but is not used by the normal stack (the brief said to remove it from the running stack; done). It carries MAIL_TRANSPORT/OWNER_EMAIL/TENANT_API_KEYS overrides for E2E only.
- test_run_flows fixture deletes its own `test-run-flows` keys on teardown.
- ROADMAP SC1 / WF-01 wording ("6 existing", "11 workflows") is superseded: 3 tenant-keyed (inbound-message, followup-scheduler, escalation-alert) + 2 allowlisted untenanted (outreach-flow, error-handler) + 5 new (quote-request, review-reply, capacity-check, daily-brief, intake-event) = 10 workflow files. The orchestrator will amend ROADMAP/REQUIREMENTS; not edited here.

## Deploy and standing notes
- Before deploy: set TENANT_API_KEYS (a key for every tenant, see finding) and OWNER_EMAIL; PUBLIC_DEMO_TENANT_ID; APP_DATABASE_URL. Stale `daily-report` still sits on the existing n8n volume (unpublish it or reset).
- At-least-once delivery for senders; brief at-most-once (re-run with force); webhook trust is internal-port only, shared secret deferred; no draft approval UI yet; n8n execution data PII is Phase 9; n8n licence decision open; GitHub Actions wiring deferred; VALIDATION.md waived.

## Self-Check: PASSED
Commits efcf0b2 and f658d10 exist; run_flows.py, test_run_flows.py, docker-compose.e2e.yml present.
