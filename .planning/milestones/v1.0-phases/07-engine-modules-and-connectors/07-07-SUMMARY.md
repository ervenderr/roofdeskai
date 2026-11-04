---
phase: 07-engine-modules-and-connectors
plan: 07
subsystem: intake
tags: [intake_event, idempotent-upsert, pii]
requires: [07-02, 07-06]
provides: [PackMeta.intake (Intake/EventMap), engine.intake (get_path, normalise_event, apply_event), POST /intake_event]
key-files:
  created: [api/app/engine/intake.py, api/app/intake_event_routes.py, api/app/test_intake_event.py]
  modified: [api/app/pack.py, api/app/main.py, api/app/tests_data/packs/demo-venue/pack.yaml]
requirements-completed: [MOD-07]
---

# Phase 7 Plan 07: intake_event webhook Summary

Pack-mapped `waiver|checkin|result` events normalise (email lowercase, phone to +digits) and upsert one row per (tenant_id, person_key) via `INSERT ... ON CONFLICT` with COALESCE name, LEAST timestamps and a result_at guard. `/intake_event` is separate from the untenanted `/intake`.

## Commits
- Task 1+2 in one commit: `feat: intake_event webhook with idempotent per-person upsert` (hash in final report)
- Summary commit hash in final report.

## Verification (real output)
- RED: `make g-test ARGS="app/test_intake_event.py -q -x"` -> `ERROR app/test_intake_event.py`, `Interrupted: 1 error during collection` (engine.intake missing).
- Green: `make g-test ARGS="app/test_intake_event.py app/test_pack_modules.py -q"` -> 60 dots, no failures.
- Full `make g-test`: `921 passed, 1 warning in 20.76s`.
- After the run: tenants `['summit-roofing', 'bright-smile-dental']`, `count(*) from intake_people` = 0 (no demo-venue row left; existing conftest cleanup sufficed).

## Coverage
Same event twice -> one row (created true then false); waiver+check-in with differently cased email -> same row; replayed waiver keeps earliest; newer result replaces, older replay and identical replay do not regress; unmapped event / bad body / missing key / wrong type / >32 KB -> 422 naming event+field+tried with no values echoed; caplog and agent_events contain no name/email/phone; roofing 404; admin key alone 401; same person_key in two tenants gives two rows (RLS). Shipped roofing/dental packs have `meta.intake is None` (pinned hash test green).

## PII note for Phase 9 data map
`intake_people.person_key` (email/phone) and `name` are PII: needs data-map entry, retention purge and delete_subject coverage. No Phase 7 action (DELETE is already granted on the table).

## Deviations from Plan
None. Pack model changes were made before the tests since they are config the tests load.

## Not verified / risks
- Evals (94/96, 43/43) not run (no roofing/dental files touched; end-of-phase gate).
- A person identified by phone in one event and email in another stays two rows (documented limit).
- Naive (timezone-less) `occurred_at` is ignored and replaced by now(), so a replay of such an event can move a result forward; intended per research, but sources should send offsets.
- Payload size is measured after JSON parse (`len(json.dumps)`), not on the raw body, so a huge body is still parsed by the framework first.
- No real n8n/webhook source exercised.

## Self-Check: PASSED
