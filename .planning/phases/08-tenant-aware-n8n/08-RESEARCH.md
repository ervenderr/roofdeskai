# Phase 8: Tenant-Aware n8n - Research

**Researched:** 2026-11-04
**Domain:** n8n 2.18.5 workflow JSON (import-on-start), FastAPI tenant/admin auth, API-only operation
**Confidence:** HIGH on n8n behaviours (all key ones were executed in throwaway containers of the pinned image), HIGH on repo facts (read from code), MEDIUM on exact HTTP-node option JSON for pass-through status codes (not executed).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tenant-aware (send `X-API-Key`, never the admin key for tenant data): `inbound-message`, `followup-scheduler`, `escalation-alert`. `daily-report` is replaced by the new `daily-brief` (retire its JSON; keep `/metrics` endpoint). `outreach-flow` and `error-handler` are RoofDesk's own untenanted tooling (TEN-06): they stay on the admin key / no API call and are listed in an explicit allowlist in the CI check, not silently skipped.
- **D-02:** New workflows (5): `quote-request`, `review-reply`, `capacity-check`, `daily-brief`, `intake-event`, all calling Phase 7 endpoints with a tenant key. Total = 3 existing tenant-aware + 2 untenanted + 5 new (supplier-order is cut-first, deferred). Workflow JSON lives in `n8n/workflows/`, imported by the existing compose entrypoint.
- **D-03:** Existing `inbound-message` and `followup-scheduler` stop relying on the admin key + default-tenant fallback (Phase 6 deviation D-06): they send the tenant key, and the API-side admin `X-Tenant-Id`/default fallback is then removed or restricted so admin-key calls without a tenant fail clearly (planner decides removal vs hard 400; roofing flows must keep working).
- **D-04:** Tenant keys never committed. Keys are issued with the Phase 6 admin endpoints and provided to n8n through an env var map (`TENANT_API_KEYS` JSON `{tenant_id: key}`) read in Code/expression nodes (`$env`), documented in `.env.example` with placeholders only. Rotating a key = updating the env. The admin key is used only for `GET /admin/tenants` and tenant-listing.
- **D-05:** Add `GET /tenant/me` (tenant key) returning `{tenant_id, slug, name, owner_email, timezone, locale, enabled_modules}` from the pack/tenants data; workflows take the owner/notification address from this response, not from hardcoded values or env. If the pack lacks an owner email field, add it to pack.yaml models (optional, validated) and set it for roofing/dental as placeholder/demo addresses - flag if this changes pack hashes (pinned hash test must be updated deliberately in the same commit, and the prompt render must stay byte-identical).
- **D-06:** Scheduled workflows (`followup-scheduler`, `daily-brief`, `capacity-check` nightly) run one trigger, call `GET /admin/tenants` (admin key), then loop per tenant (Split In Batches) using that tenant's key. The API decides who is due: `POST /daily-brief/due` for briefs; follow-up and capacity use the existing due/range endpoints. n8n never computes tenant-local time. Fix the Phase 7 warning: `/daily-brief/due` with admin key + nonexistent tenant id must return 404 not 500.
- **D-07:** Add `scripts/run_flows.py` (and `make run-flows`) that performs the same API call sequences as the workflows (list tenants, per-tenant due/draft/send via the API, mail through the existing mailer) with no n8n. A pytest runs it against the test client/branch API with n8n absent and asserts a booking, escalation notification, follow-up and brief complete. The API's escalation notifier must not require n8n: if `ESCALATION_WEBHOOK_URL` is unset or fails, it logs and falls back to direct mail via the existing mailer (planner confirms how escalation delivery works today).
- **D-08:** A pytest (`test_n8n_workflows.py`) parses every `n8n/workflows/*.json`: every HTTP Request node whose URL targets `$env.API_URL` must carry an `X-API-Key` header (or, for the allowlisted untenanted workflows, `X-Admin-Key`), listed explicitly; every workflow referenced in the catalog exists; no committed secrets (no `rd_live_` strings). Also runs via `make check-n8n`. No GitHub Actions needed.
- **D-09:** Verify new workflows in the branch compose stack (n8n + mailpit) by importing, triggering webhooks/manual executions, and checking mailpit/API state; evidence captured in the SUMMARY. If n8n cannot be driven headlessly, fall back to schema/CI checks plus `run_flows.py` equivalence tests and say so explicitly.

### Claude's Discretion
Exact webhook paths, node layout, Code-node snippets, batching sizes, email templates, whether `daily-report.json` is deleted or left disabled, `/tenant/me` field details, plan split (expect ~5-6 plans).

### Deferred Ideas (OUT OF SCOPE)
- supplier-order workflow (v2); appointment reminders, knowledge-gap loop, nightly eval run (v2 backlog)
- GitHub Actions wiring for the CI check; per-tenant n8n credentials UI; n8n licence decision
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WF-01 | Existing workflows tenant-aware (tenant key header, owner address from API) | Sections 1, 3, 4: per-workflow edit table, `/tenant/me`, key-map pattern (verified in n8n 2.18.5) |
| WF-02 | quote-request, review-reply, capacity-check, daily-brief, intake-event run | Section 6: webhook paths, payload mapping, approved-draft sender, `drafts/{id}/sent` addition |
| WF-03 | Scheduled workflows loop `GET /admin/tenants`; API decides due | Section 6 + pitfalls: SplitInBatches loop pattern verified, empty-output trap |
| WF-04 | Platform runs through the API with n8n off | Sections 2, 7: escalation mail fallback, `run_flows.py` design |
| WF-05 | CI fails when an API-calling HTTP node lacks the key header | Section 8 |
</phase_requirements>

## Summary

n8n is pinned only by tag `n8nio/n8n` (compose has no version; the local image is 2.18.5, `latest` at pull time). In 2.x `N8N_BLOCK_ENV_ACCESS_IN_NODE` defaults to **true**; compose already sets it to `"false"`. I proved both directions by running the pinned image: with it `false`, `JSON.parse($env.TENANT_API_KEYS)[id]` works in a Code node and in a `={{ }}` expression; with it unset, the Code node fails with `access to env vars denied`. So D-04 (env key map) works with no compose change beyond passing `TENANT_API_KEYS` into the n8n service. The SplitInBatches loop with `$('With key').first().json.key` header expressions also works (verified, two tenants, keys do not cross).

The API already has most of what is needed: tenant-scoped `require_scope` on the three legacy routes, Phase 7 routes on `require_tenant`, `GET /admin/tenants`, `POST /daily-brief/due` (tenant-scoped with a tenant key), and `PackMeta.owner_email` **already exists** (optional, set in no shipped pack). So `/tenant/me` can return `pack.meta.owner_email or settings.owner_email` and **no pack file changes, no hash change** (pinned in `test_pack_modules.PINNED`). Three small API additions are needed: `/tenant/me`, a `POST /drafts/{id}/sent` transition (no endpoint exists; `sent` is only an allowed status value), and a recipient address on quote drafts (the draft stores no `to`). Escalation delivery today is API -> `ESCALATION_WEBHOOK_URL` (n8n) for web-channel only, swallowing failures; add the mailer fallback there.

Biggest practical risks: (a) loop termination when a per-tenant branch emits zero items (verified: the loop silently stops and later tenants are skipped; fix with `alwaysOutputData` plus a gate), (b) roofing and dental packs have **no module blocks**, so every new workflow can only be proven end to end on a `demo-venue` tenant, which is not in the live `./businesses` mount, (c) `n8n execute` cannot start schedule-only workflows (verified `Missing node to start execution`); give scheduled workflows a Manual Trigger.

**Primary recommendation:** Do API groundwork first (`/tenant/me`, `drafts/{id}/sent`, escalation mail fallback, due-404), migrate the three existing workflows with the verified key-map/SplitInBatches pattern, land the CI check before the new workflows, flip the admin fallback to a hard 400 last, then prove with `run_flows.py` plus a headless branch-stack run on a demo-venue tenant.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Which tenants exist / are due | API | n8n (loop only) | `GET /admin/tenants`, `/daily-brief/due`; n8n never computes local time |
| Tenant credential selection | n8n (env map lookup) | API (validates key) | n8n only picks a key by tenant id; API derives the tenant from the key |
| Owner/notification address | API (`/tenant/me`) | n8n (reads) | Single resolver: pack field, else env |
| Quote/review/brief/capacity decisions | API | - | Phase 7 modules, unchanged |
| Approval of drafts | API (`/drafts/*`) | human via API/dashboard | n8n never approves |
| Sending approved drafts / alerts | n8n (HTTP to mail) | `run_flows.py` + `mailer.py` when n8n off | "n8n triggers and sends" |
| Escalation alert fallback | API (`mailer`) | n8n | Must work with n8n off |
| CI header check | Test (python, parses JSON) | Makefile | Static check, no n8n needed |

## Standard Stack

No new libraries. [VERIFIED: repo `api/requirements.txt`]

| Tool | Version | Purpose |
|------|---------|---------|
| n8n image | `n8nio/n8n` tag floats; local image **2.18.5** [VERIFIED: `docker exec ... n8n --version`] | Orchestration; recommend pinning `n8nio/n8n:2.18.5` in compose so JSON semantics cannot drift |
| stdlib `json`, `re`, `pathlib` | py3.12 | CI check parser |
| `httpx==0.27.*` (existing) | | `run_flows.py` client; `TestClient` is httpx-compatible |
| `api/app/mailer.py` (existing) | | n8n-off mail path |

### Package Legitimacy Audit
No external packages are installed in this phase. slopcheck not run (not applicable). Packages removed: none. Flagged: none.

## Architecture Patterns

### System Architecture Diagram

```
 external trigger                n8n (optional)                         FastAPI (decides)                 out
 ----------------                --------------                         -----------------                 ---
 SMS/GHL webhook ----> inbound-message --(X-API-Key from env map)--> POST /webhooks/inbound
                          | outcome=booked --> GET /tenant/me --> mailpit (customer confirmation)
                          | outcome=escalated --> escalation-alert
 web chat escalation --(API posts {tenant_id,conversation_id,reason,link})--> escalation-alert
        \--(webhook unset/failed)--> mailer.send(owner)  <== NEW fallback, no n8n
 escalation-alert: env map -> GET /tenant/me -> owner_email -> mailpit
 cron (hourly/nightly/15min) -> [Manual Trigger twin] -> GET /admin/tenants (X-Admin-Key, only call using it)
        -> SplitInBatches(1) -> "With key" Code (env map lookup) -> per-tenant API calls (X-API-Key)
              followup: GET /admin/followups/due -> POST .../draft -> mail
              brief:    GET /tenant/me -> POST /daily-brief/due -> POST /daily-brief -> mail owner
              capacity: GET /tenant/me -> POST /capacity/check -> mail owner on new|reflagged
              drafts:   GET /drafts?status=approved&kind=... -> mail -> POST /drafts/{id}/sent (NEW)
 webhooks quote-request / review-reply / capacity-check / intake-event -> tenant key -> Phase 7 route -> owner notice / respond
 scripts/run_flows.py: same sequences with httpx + mailer.send, no n8n
```

### Recommended structure
```
n8n/workflows/   inbound-message, followup-scheduler, escalation-alert, outreach-flow, error-handler (existing, edited as noted)
                 quote-request, review-reply, capacity-check, daily-brief, intake-event (new); daily-report.json deleted
api/app/tenant_routes.py   GET /tenant/me
api/app/test_tenant_me.py, test_n8n_workflows.py, test_run_flows.py
scripts/run_flows.py
```
Workflow `id` must equal the file basename (compose does `publish:workflow --id=$(basename $f .json)`). [VERIFIED: docker-compose.yml, `n8n list:workflow`]

### Pattern 1: Tenant key lookup in n8n 2.18.5 [VERIFIED by executing the image]
```js
// Code node "With key" (typeVersion 2, run once for all items). Throws loudly on a missing key.
const keys = JSON.parse($env.TENANT_API_KEYS || '{}');
const id = $input.first().json.id;            // tenant id
if (!keys[id]) throw new Error('no key for tenant ' + id);   // never log the map
return [{ json: { id, key: keys[id] } }];
```
HTTP Request header (works in expressions too): `{"name":"X-API-Key","value":"={{ $('With key').first().json.key }}"}`.
Use `.first()`, not `.item`: with SplitInBatches batchSize 1 each iteration has exactly one item, `.first()` returned the right key for every downstream node including after a fan-out HTTP node (executed: t1->K1, t2->K2, no crossing). `{{ JSON.parse($env.TENANT_API_KEYS)[$json.tenant_id] }}` as a direct header expression also works (executed) and is the simplest for **single-item webhook flows** (inbound, escalation, quote-request): no Code node needed, but then the CI regex must accept `TENANT_API_KEYS` in the header value (see section 8).

Compose: add `TENANT_API_KEYS: ${TENANT_API_KEYS:-}` to the `n8n` service env (do not write `:-{}`, brace parsing is ambiguous). Keep `N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"` (already set; REQUIRED, default in 2.x is true and fails with `access to env vars denied`) [VERIFIED executed; CITED n8n 2.0 breaking-changes]. Keep `ADMIN_API_KEY` in n8n env (used only for `GET /admin/tenants` and outreach-flow).

### Pattern 2: Per-tenant scheduled loop [VERIFIED]
```
Schedule trigger ┐
Manual Trigger   ┴-> GET /admin/tenants (X-Admin-Key) -> Split In Batches v3 (batchSize 1)
   output 1 "loop" -> With key -> ...per-tenant nodes... -> back to Split In Batches
   output 0 "done" -> (nothing)
```
SplitInBatches v3: output index 0 = done, 1 = loop (executed that way). `GET /admin/tenants` returns a JSON array; the HTTP node splits it into one item per tenant. Any node in the per-tenant branch that can emit zero items (empty `due` list, `[]` from a Code gate) **terminates the whole loop** and later tenants are never processed [VERIFIED: loopA run produced no iteration for t2]. Fix [VERIFIED loopB]: set `"alwaysOutputData": true` on every node that may return nothing (HTTP list calls, gate Code nodes) and follow it with a gate that routes "nothing to do" back to the Split node. The final node of every branch must connect back to Split In Batches.

### Pattern 3: Manual twin for headless runs [VERIFIED]
`n8n execute --id=X` on a schedule-only workflow fails `Missing node to start execution`. Add a `n8n-nodes-base.manualTrigger` wired to the same first node in each scheduled workflow. `n8n execute --id=X --rawOutput` then works (executed with a manual-trigger workflow, `status: success`).

### Anti-Patterns
- HTTP calls from Code nodes (`this.helpers.httpRequest`/`fetch`): invisible to the CI check. Forbid in the check.
- Per-tenant n8n Header Auth credentials (not selectable by tenant id).
- Branching on tenant-local time in n8n.
- A literal tenant id or key anywhere in JSON.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Due-ness of briefs | local-time cron math in n8n | `POST /daily-brief/due` (is_due window = send_hour .. +3h, once per local date) |
| Dedupe/idempotency of quotes, flags, briefs, intake | n8n static data | Phase 7 server idempotency (draft input_hash, capacity input_hash, brief_runs per date, intake upsert) |
| Mail | new transport | `mailer.send` (API/n8n-off); mailpit HTTP node (n8n) |
| Approval state | n8n wait nodes | `drafts` table + `/drafts/{id}/approve` |

## 1. Per-workflow current structure and minimal edits

Common: all HTTP nodes are `httpRequest` v4.2; headers are `headerParameters.parameters`; mail nodes POST JSON to `http://mailpit:8025/api/v1/send` with hardcoded `no-reply@summitroofing.test`/`owner@summitroofing.test`/`human@summitroofing.test`. [VERIFIED: JSON read]

| Workflow | Nodes today | Minimal edits |
|---|---|---|
| inbound-message (webhook `inbound-message`, responseMode responseNode) | Webhook -> Normalize payload (Code, onError continueErrorOutput) -> Call agent (POST `/webhooks/inbound`, `X-Admin-Key`, retry 3) -> [Send reply (respond), Route by outcome (switch: booked / escalated / nurture / other)]; booked -> Has email? (Code) -> Email booking confirmation (mailpit, text hardcodes "roof inspection ... Summit Roofing"); escalated -> Alert a human (executeWorkflow `escalation-alert`); errors -> Reject bad payload 400 / Agent unavailable 502 -> Raise failure | (a) Normalize: read `tenant_id` from `b.tenant_id ?? $json.query.tenant_id`; throw if absent; emit it in output **but strip it before the API body** (body is `JSON.stringify($json)` and `InboundIn` has no tenant field; unknown fields are ignored by pydantic default, still strip). Easiest: Call agent body `={{ JSON.stringify({contact_id:$json.contact_id,message:$json.message,channel:$json.channel,message_id:$json.message_id}) }}`. (b) Call agent header -> `X-API-Key` = `={{ JSON.parse($env.TENANT_API_KEYS)[$('Normalize payload').first().json.tenant_id] }}`. (c) Before Email booking confirmation add `GET /tenant/me` (same header) and replace hardcoded From/subject/body with `me.name`, neutral text ("Your appointment is booked"). (d) Alert a human: pass `{tenant_id, reason: escalation_reason, conversation_id, link}`; escalation-alert's normalizer already reads `escalation_reason`. Note: the API already emails the lead and owner on booking (`agent._notify_booking`), so the n8n confirmation duplicates; keep (minimal) but see Open Question 4. |
| followup-scheduler (cron `0 2 * * *`) | Nightly -> Find due (GET `/admin/followups/due?hours=48`, admin) -> Draft (POST `/admin/followups/{cid}/draft`, admin) -> Send email (mailpit, hardcoded From) | Rebuild per Pattern 2: Nightly+Manual -> GET `/admin/tenants` (admin) -> Split(1) -> With key -> GET `/tenant/me` -> Find due (tenant key; `alwaysOutputData`) -> Gate (IF `$json.conversation_id` exists, else back to loop) -> Draft (tenant key) -> Send email (From name = `me.name`, To `$json.to`) -> back to loop. Cadence stays `hours=48` in the URL (no pack cadence exists; `MAX_FOLLOWUPS=3` is a module constant). |
| escalation-alert (webhook `escalation-alert` responseMode onReceived; also executeWorkflowTrigger) | two triggers -> Normalize alert (Code: reason, conversation_id, link) -> Notify human (mailpit, To `human@summitroofing.test`) | Normalize also emits `tenant_id`; throw if missing. Add `GET /tenant/me` (header from env map by tenant_id); gate: no `owner_email` -> throw (error-handler mails you) ; Notify human To = `me.owner_email`, From name `me.name`. The API's webhook payload must start carrying `tenant_id` (section 2). |
| daily-report (cron 0 8, GET `/metrics` admin, summarize, mailpit to `owner@summitroofing.test`) | | Delete the JSON (D-01). `/metrics` endpoint stays. Compose imports whatever is in the folder; n8n's DB volume keeps the old imported workflow: add a one-time `n8n unpublish:workflow --id=daily-report` is NOT needed on a fresh volume, but on an existing `n8ndata` volume the old workflow stays active. Document `docker compose down -v` for the branch stack or `n8n delete`-equivalent via UI. [ASSUMED: no CLI delete verified] |
| outreach-flow (6 lanes, 927 lines) | all API nodes `X-Admin-Key`; mail nodes hardcoded | No change (allowlisted, TEN-06). |
| error-handler | errorTrigger -> Code -> mailpit hardcoded `owner@roofdeskai.test` | No change (no API call). |

## 2. Escalation delivery path today and the no-n8n fallback

Today: `agent._escalate` -> `tools.run(escalate_to_human)` -> `tools.escalate_to_human` inserts into `escalations`, sets state, writes an `agent_events` row, then `_notify_escalation`: **returns immediately if `ESCALATION_WEBHOOK_URL` is empty**; looks up the conversation channel; **only `channel == 'web'` posts** `{conversation_id, reason, link}` (no tenant id, no customer data) to the webhook with a 3 s timeout; `httpx.HTTPError` is logged and swallowed. sms/email channels rely on n8n's inbound branch. Compose default sets the URL to `http://n8n:5678/webhook/escalation-alert`. [VERIFIED: tools.py 138-163, docker-compose.yml]

Change (tools.py only): add `tenant_id` to the posted payload; restructure to

```python
def _notify_escalation(conversation_id, reason, tenant_id):
    channel = ...  # unchanged lookup; non-web still returns early
    if channel != "web": return
    payload = {"tenant_id": str(tenant_id), "conversation_id": ..., "reason": reason, "link": ...}
    if settings.escalation_webhook_url:
        try:
            r = httpx.post(settings.escalation_webhook_url, timeout=3, json=payload); r.raise_for_status(); return
        except httpx.HTTPError as e: log.warning(...)
    _mail_owner(payload, tenant_id)   # fallback: unset OR failed
```
`_mail_owner` resolves `owner_email` through the shared resolver (section 3); if none, `log.warning("no owner email")` and return; `mailer.send(owner, f"Escalation ({reason}): conversation {id}", "...Transcript: {link}")` inside `try/except mailer.MailError: log.exception`. Never raises (handoff must not break). Pitfalls: (1) existing tests set `escalation_webhook_url=""` (test_admin, test_leak, test_routes_scope); the fallback now runs there, so the resolver must return None when `settings.owner_email` is empty (default) and the tests that set owner_email must not email a real inbox (`no_real_mail` fixture forces mailpit transport; MailError is caught). (2) If n8n received the webhook but failed after returning 2xx, no fallback fires; error-handler covers it. (3) A dual alert is possible only if the webhook errors after processing; acceptable.

## 3. Owner address: where it lives and the `/tenant/me` design

Today (no per-tenant owner anywhere): `settings.owner_email` (env `OWNER_EMAIL`, compose default empty) is global and used by `agent._notify_booking`, `triage._alert`, `pilot`; `PackMeta.owner_email: str | None = None` exists (Phase 7) and is set in **no** shipped pack (grep of `businesses/*` empty) and only in the test `test_reviews.py:72`; n8n JSON hardcodes `human@summitroofing.test`, `owner@summitroofing.test`, `owner@roofdeskai.test`. `tenants` table columns: id, slug, name, timezone, pack_slug, created_at (no owner). [VERIFIED]

**Recommendation (one design):** resolver `owner_email(pack) = pack.meta.owner_email or settings.owner_email or None` placed in `api/app/tenants.py` (pure, no HTTP). `GET /tenant/me` (`Depends(require_tenant)`, new `tenant_routes.py`, included in `main.py`) returns:
```json
{"tenant_id": "...", "slug": "summit-roofing", "name": "Summit Roofing", "owner_email": "x@y" | null,
 "timezone": "America/Denver", "locale": "en-US",
 "enabled_modules": ["services","capacity","connectors","reviews","intake"]}
```
sourced from `get_pack(tenant)` (`meta.business`, `meta.timezone`, `meta.locale`, `meta.owner_email`; modules = those whose block is not None: `pack.services`, `pack.capacity`, `pack.connectors`, `pack.meta.reviews`, `pack.meta.intake`) plus the `tenants` row for `slug`. **Do not edit roofing/dental pack YAML**: this deviates from D-05's "set it for roofing/dental as placeholder" on purpose, because any pack file change alters `pack_hash` (hashes every non-scenario file) and breaks `PINNED` in `test_pack_modules.py` and risks the 94/96 gate evidence; the per-tenant override path exists (`pack.yaml owner_email:`) for real onboarding. Per-tenant addresses in the demo come from env (`OWNER_EMAIL`) until a real owner is set; for E2E, set `OWNER_EMAIL=owner@example.test` for the branch stack. Optionally have `agent._notify_booking` use the same resolver (one-line change; `test_agent` monkeypatches `settings.owner_email`, still compatible). `PackMeta` has no email validator; if you want validated, add a simple `field_validator` (does not change bytes). `PackMeta` uses `extra="forbid"` semantics (class `M`), so unknown YAML keys already fail.

Test (RED first): 401 without key; tenant A key returns A's slug only; roofing `enabled_modules == []`; demo-venue lists reviews, intake, services, capacity, connectors; owner falls back to env and is overridden by pack field (use `model_copy` pattern from test_reviews).

## 4. Removing the admin default-tenant fallback

Current: `admin._write_tenant(scope, route)` returns `scope.tenant_id` else logs a warning and returns `settings.default_tenant_id`. `require_scope`: `X-API-Key` present -> tenant (ignores `X-Tenant-Id`); else admin key, with optional valid `X-Tenant-Id` (400 if malformed) else `Scope(None, True)`. [VERIFIED: auth.py, admin.py]

Routes in `admin.py` (all `Depends(require_scope)`):
| Route | Admin w/o tenant today | After change |
|---|---|---|
| GET /leads, /leads/{id}, /conversations, /conversations/{id}, /metrics, /admin/escalations, /admin/followups/due | cross-tenant read (dashboard relies on this: `dashboard/lib/data.ts` calls `/metrics`, `/conversations` with the admin key) | unchanged |
| POST /admin/escalations/{eid}/resolve | `_write_tenant` -> default tenant | 400 |
| POST /webhooks/inbound | default tenant | 400 |
| POST /admin/followups/{cid}/draft | default tenant | 400 |

**Recommendation:** remove the default only (hard 400 `"tenant required: send X-API-Key, or X-Admin-Key with X-Tenant-Id"` from `_write_tenant`, drop the `log.warning`), keep explicit admin + `X-Tenant-Id` for operator use (tests and `test_keys` rely on it; D-03 allows "restricted"). `settings.default_tenant_id` stays (triage uses it; tests use it; backfill migration). Callers affected: n8n inbound-message and followup-scheduler (moved to tenant keys), no dashboard write call hits these three routes, `scripts/` none. Tests affected: `test_admin.py` (headers `H` = admin only on inbound x6, followups draft x2, resolve x2 -> add `"X-Tenant-Id": settings.default_tenant_id` to `H`, tests-only), `test_routes_scope.py:176-184` (explicit test of the fallback: replace by "admin without tenant -> 400" and assert nothing written), and any test posting `/webhooks/inbound` with `ADMIN` only (lines 167-183). Do this flip in the same plan as (or after) the workflow migration; run `grep -rn "X-Admin-Key" n8n/workflows` and the CI check to prove no tenant-aware workflow still uses it for those routes. Update CLAUDE/docs `docs/deploy.md` line 34 stays valid.

## 5. `/daily-brief/due` 404 fix

`due()` with admin scope and `X-Tenant-Id: <nonexistent uuid>` builds `tids=[that id]`; `_due_for` calls `get_pack`, which raises `PackError("... no pack_slug")` for an unknown tenant, caught -> `None` -> `{"due": []}`. By code reading this returns **200 empty, not 500** (W6 says "may 500"); either way the requirement is 404. Fix in `due()`: when `scope.tenant_id` is set and `scope.is_admin`, check `SELECT 1 FROM tenants WHERE id=:t` via `system()` and `raise HTTPException(404, "tenant not found")` (mirror `tenant_admin._tenant`). Tenant-key scope needs no check (key implies existence). Write the RED test first and record actual pre-fix status in the SUMMARY; also catch non-PackError exceptions per-tenant in the loop (`log.exception`, skip) so one broken pack cannot 500 the whole admin listing. [VERIFIED by reading; not executed]

## 6. New workflows

Auth: every API call uses `X-API-Key`. Tenant selection for webhooks: `tenant_id` in the JSON body or `?tenant_id=` query (`$json.body.tenant_id ?? $json.query.tenant_id`), validated by a Code step (UUID regex) and looked up in the env map. Webhook trust: the caller chooses which tenant's key n8n uses, so webhooks are not safe on a public port (existing posture, `docs/deploy.md` "do not publish"); see Open Question 5.

Common head for per-tenant scheduled lanes: Schedule + Manual -> `GET /admin/tenants` -> Split(1) -> With key -> `GET /tenant/me` -> IF `enabled_modules` contains the module (else back to loop).

### quote-request
- Webhook `POST /webhook/quote-request`, body `{tenant_id, email_text, contact_email?}` (or structured `{tenant_id, request:{service_id,qty,add_on_ids,customer_type}, contact_email}`), responseMode responseNode.
- Normalize (Code) -> `POST /quotes` with body `{email_text}` or `{request}` plus (NEW, section below) `contact_email`. Note `QuoteBody` has `extra="forbid"`: strip `tenant_id` before sending. The LLM extraction + email take up to ~2 x 60 s timeouts: set the HTTP node timeout to 120000 ms.
- Response: `{id, status, deduped, payload}`; respond `{draft_id, status, deduped}`. If `status` in (`pending`,`needs_human`) and not deduped: `GET /tenant/me` -> mail owner "Quote draft #id waiting for approval" (no customer text in the mail; reference the draft id).
- Second lane (same workflow): Schedule `*/15 * * * *` + Manual -> tenants loop -> `GET /drafts?status=approved&kind=quote` (alwaysOutputData) -> per draft: To `payload.contact_email`, body `payload.email_text` (skip + leave approved if `contact_email` missing) -> mailpit send -> `POST /drafts/{id}/sent` (NEW) -> back to loop. Only `approved` drafts are ever sent; `needs_human` quotes are never sent (no `email_text` guaranteed).
- Approval: `POST /drafts/{id}/approve|reject` with the tenant key (curl/ops/dashboard); there is no draft UI yet (out of scope, note in SUMMARY).

### review-reply
- Webhook `POST /webhook/review-reply`, body `{tenant_id, review_text, rating, platform}` -> `POST /reviews/draft` (strip `tenant_id`; model `extra="forbid"`; rating int 1-5, platform google|tripadvisor|other) -> mail owner "Review reply draft #id ready for approval" (include `payload.reply_text` or the `violations` codes; owner address from `/tenant/me`). Reviews are never posted anywhere, so "send" = after approval, mail the final reply text to the owner to paste: second lane `GET /drafts?status=approved&kind=review_reply` -> mail owner -> `POST /drafts/{id}/sent`.
- "Scheduled poll" in the spec has no data source in the repo (no review connector); the scheduled lane polls approved drafts only. State this in the SUMMARY; do not invent a review fetcher.

### capacity-check
- Webhook `POST /webhook/capacity-check` body `{tenant_id, bookings:[{start, covers}], staff_overrides?, first?, last?}` (new booking) and a nightly `0 3 * * *` + Manual lane with body `{}` (uses the bookings connector; mock today).
- `POST /capacity/check` -> response `{checked_shifts, flags:[{flag_key, kind, shift_id, date, staff, covers, capacity, status}], resolved}`; filter `status in (new, reflagged)` (the API already classifies; `unchanged` must not re-alert) -> mail owner one message listing flags. A response with `source_unavailable` -> no mail (flags untouched by design). 422 "no booking source" and 404 "module not enabled" are avoided by the `enabled_modules` gate (capacity) in the nightly lane; the connectors check is inside the API (nightly call may still 422 for a tenant with capacity but no bookings source: set `neverError` on the node and treat non-200 as skip; this is the one place a status pass-through is needed [ASSUMED option shape: `options.response.response.neverError=true, fullResponse=true` giving `$json.statusCode`/`$json.body`; verify by import + curl in the plan]).

### daily-brief
- Cron `0 * * * *` + Manual -> tenants loop -> With key -> `/tenant/me` gate (`connectors` in modules AND `owner_email` present; do this BEFORE generating the brief, because `POST /daily-brief` writes `brief_runs` and makes the tenant not-due for the local date, so a missed send is silent) -> `POST /daily-brief/due` with the **tenant key** (tenant scope returns only that tenant; `due` list empty -> skip, `alwaysOutputData` + gate) -> `POST /daily-brief` (tenant key, empty body) -> mailpit send To owner, Subject `Daily brief {local_date}: {name}`, `Text: payload.text`, `HTML: payload.html` (mailer.py already sends both fields to mailpit) -> back to loop. Replaces daily-report; D-04 holds (admin key only for the tenant list).
- Residual risk: at-most-once (mail failure after the brief row is written). Mitigation: error-handler alert; a human can `POST /daily-brief {"force":true}`; record in SUMMARY.

### intake-event
- Webhook `POST /webhook/intake-event`, body `{tenant_id, event: waiver|checkin|result, payload:{...}}` -> `POST /intake_event` with `{event, payload}` (strip `tenant_id`) -> respond with the API status/body. No mail. Needs status pass-through so a 422 mapping error reaches the sender (`neverError` + `fullResponse`, respond `responseCode: ={{ $json.statusCode }}`) [ASSUMED option names, verify]. Do not log payloads (PII); consider workflow setting `saveDataSuccessExecution: "none"` for this workflow (documented n8n workflow setting, [ASSUMED]; Phase 9 owns retention).

### API additions (flag for planner; not in Phase 7)
1. `POST /drafts/{id}/sent` in `drafts.py`: `_decide(tenant, id, "sent", ("approved",))`; 409 if not approved; emits `draft_decided` event (reuse). `list_drafts` already accepts `status=sent`; migration already allows `sent`. No schema change.
2. Quote recipient: add optional `contact_email: str | None = Field(None, max_length=254)` (simple `@` pattern validator, no new dependency) to `QuoteBody`; store as `payload["contact_email"]`; **keep it out of the dedupe hash basis** (it is not part of the quote). Note the existing `payload["customer_email"]` holds the raw email *text*, not an address (misnomer; do not reuse).
3. Delivery is at-least-once: n8n sends, then marks sent; a crash between the two re-sends next run. Accept and record (alternative: mark-first loses mail on failure).
These are the only "new engine" touches; they are plumbing, not decision logic.

## 7. `scripts/run_flows.py` and the n8n-off test

Location: `/srv/scripts` is a writable bind mount and cwd is `/srv`, so `import scripts.run_flows` works from pytest (namespace package, no `__init__`). [VERIFIED: Dockerfile WORKDIR /srv, compose volumes]

Design: a module with functions taking `(client, mail, keys)`: `client` is an `httpx.Client(base_url=API_URL)` for the CLI or a Starlette `TestClient` in pytest (same API), `mail` is `mailer.send` (injectable), `keys` is the parsed `TENANT_API_KEYS`. Functions mirror workflows 1:1:
- `inbound(client, keys, tenant_id, contact_id, message, message_id=None)` -> POST `/webhooks/inbound` (tenant key); if `outcome == "escalated"` -> `escalation_alert`; if `booked` and `email` -> mail confirmation.
- `escalation_alert(client, keys, mail, tenant_id, conversation_id, reason, link)` -> `/tenant/me` -> mail owner.
- `followups(client, admin_key, keys, mail)` -> `GET /admin/tenants` (admin) -> per tenant due -> draft -> mail.
- `daily_brief(...)`, `capacity_nightly(...)`, `send_approved(...)` same shape.
- `main()` runs `followups`, `daily_brief`, `capacity_nightly`, `send_approved` once (cron-able); `python -m scripts.run_flows [name]`; `make run-flows` = `$(GCOMPOSE) exec -T api python -m scripts.run_flows`. No n8n import, no n8n URL. Keep under ~150 lines.

Pytest `test_run_flows.py` (n8n absent: set `settings.escalation_webhook_url=""`, or a closed port to cover the fail path): reuse `test_agent.script` style fake `llm.chat` (a booking needs two scripted turns: `FULL` then `{"reply":"ok"}`, then `"the first"`; an escalation needs none: `"let me speak to a real person"` hits `policy.escalation_reason` before the model). Two tenants with keys (`auth.issue_key`), `monkeypatch` `mailer.send` into a list. Assert: (1) booked -> conversation `DONE/booked`, appointment row, customer mail captured; (2) web `/chat` escalation with webhook unset -> exactly one owner mail via the section 2 fallback; sms escalation through `inbound` -> `escalation_alert` mail; (3) NURTURE conversation 48h+ idle -> `followups` -> one mail and `followup_count == 1` (insert fixture rows as in `test_admin.py:51-70`); (4) demo-venue tenant: `daily_brief` with `brief_routes.utcnow` patched to 07:00 local -> mail with text, second run mails nothing. Use `ADMIN`+tenant keys only; assert no call used `X-Admin-Key` except `/admin/tenants` (inspect via a wrapper client). Env for the module: `API_URL`, `ADMIN_API_KEY`, `TENANT_API_KEYS` (same names as n8n).

## 8. `test_n8n_workflows.py` CI check

Location `api/app/test_n8n_workflows.py` (consistent with other tests; named in D-08). Needs the workflows visible in the api container: **add `./n8n:/srv/n8n:ro` to the `api` service volumes** (currently only `app, prompts, clients, businesses, site, db, evals, scripts` are mounted). Locate the folder as `next(p for p in Path(__file__).resolve().parents if (p / "n8n" / "workflows").is_dir()) / "n8n" / "workflows"` (works on host and in container). `conftest.py` has session-autouse DB fixtures, so run via the container (`make check-n8n` = `$(GCOMPOSE) exec -T api python -m pytest -q app/test_n8n_workflows.py`); host has no pytest installed [VERIFIED: `No module named pytest`].

What to parse (stdlib `json`, `re`), per file:
1. Catalog: `EXPECTED = {inbound-message, followup-scheduler, escalation-alert, outreach-flow, error-handler, quote-request, review-reply, capacity-check, daily-brief, intake-event}` equals the set of basenames; `daily-report` absent; each JSON `id` equals basename (compose publish depends on it); `settings.errorWorkflow == "error-handler"` for all except error-handler itself.
2. For every node with `type == "n8n-nodes-base.httpRequest"`: `url` (strip a leading `=`). It "targets the API" if it contains `$env.API_URL` or `api:8000` or `localhost:8000`. Non-API URLs (mailpit) need no key but must not carry `X-Api-Key`.
3. API nodes in tenant-aware workflows (everything not in `UNTENANTED = {"outreach-flow", "error-handler"}`): require `sendHeaders` true and a header named `X-API-Key` (case-insensitive) whose value starts with `=` and references `TENANT_API_KEYS` or `$('With key')` (never a literal; also fail on `rd_live_`). Exception, pinned by name: a node whose method is GET and whose url ends with `/admin/tenants` may use `X-Admin-Key` with `$env.ADMIN_API_KEY` (and nothing else may use `ADMIN_API_KEY`). Fail on any `X-Tenant-Id` header (impersonation), any `authentication`/`genericAuthType` other than none, and any API node without headers.
4. Allowlisted untenanted workflows: every API node must carry `X-Admin-Key` (value `$env.ADMIN_API_KEY`); assert the allowlist entries exist (a deleted file must not silently shrink the list) and that `error-handler` has zero API nodes.
5. Bypass guard: any `n8n-nodes-base.code` node whose `jsCode` contains `helpers.httpRequest`, `fetch(`, `$http`, or `api:8000` fails.
6. Secrets: scan raw file text for `rd_live_` and for a long hex/base64 token next to `ADMIN_API_KEY`; none allowed. `.env.example` contains no real keys (`TENANT_API_KEYS={}` placeholder only).
Also add parametrized negative tests with in-memory mutated copies (header removed, wrong header, literal key) asserting the checker function fails, so the check cannot rot into always-green.

## 9. Can n8n be driven headlessly here? Yes, with these constraints

Verified facts [VERIFIED by executing]: the branch stack's n8n (container `roofdesk-global-n8n-1`, host port 15679) is healthy (`/healthz` -> `{"status":"ok"}`); unknown webhook paths 404; mailpit API is on host 18025 (`/api/v1/messages`, 500 messages already present: filter by subject/recipient, or delete first with `DELETE /api/v1/messages`). CLI commands present: `import:workflow`, `publish:workflow`, `list:workflow`, `execute --id`, `export:workflow`, `export:entities`. No `sqlite3` binary, so executions are not readable directly; the public REST API needs an API key created in the UI, so do not rely on it.

Exact commands (branch stack, `GCOMPOSE="docker compose -p roofdesk-global -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.global.yml"`):
```bash
# 0. keys: issue per tenant with the admin key, export as the env map for n8n
curl -s -X POST -H "X-Admin-Key: $ADMIN_API_KEY" localhost:<api-port>/admin/tenants/$TID/keys   # api port is NOT published in override; use: $GCOMPOSE exec -T api curl ... or python
export TENANT_API_KEYS='{"<tid-a>":"rd_live_...","<tid-b>":"rd_live_..."}'
# 1. import + publish: recreate n8n so the entrypoint re-imports /workflows
$GCOMPOSE up -d --force-recreate n8n        # compose entrypoint: import:workflow --separate, publish each, start
$GCOMPOSE exec -T n8n n8n list:workflow
# 2. webhook flows (tenant-aware): plain curl
curl -s -X POST localhost:15679/webhook/inbound-message -H 'content-type: application/json' -d '{"tenant_id":"<tid>","contact_id":"c1","message":"let me speak to a real person"}'
curl -s -X POST localhost:15679/webhook/intake-event -d '{...}'
# 3. scheduled flows: manual twin
$GCOMPOSE exec -T n8n n8n execute --id=daily-brief --rawOutput | tail -5
# 4. evidence
curl -s "localhost:18025/api/v1/search?query=subject:Daily" | jq '.messages[].Subject'
$GCOMPOSE exec -T api python -c "...SELECT status FROM drafts..."   # or GET /drafts with the tenant key
```
Notes: the `api` service has `ports: !reset []` in `docker-compose.override.yml`, so the API is not reachable from the host; run API-side curls via `$GCOMPOSE exec -T api python -c` (httpx) or `docker run --network`. `TENANT_API_KEYS` must be in the **host shell or `.env`** when recreating n8n (compose interpolation) [VERIFIED pattern in compose]. An imported workflow's webhook only works after `publish:workflow` (the entrypoint does this); `n8n execute` runs in a separate process on the same SQLite file as the running server (works in practice for a short run; if it errors with a DB lock use `docker run` with a copied volume instead [ASSUMED]).

**Module data constraint (important):** roofing and dental packs have no `services/capacity/connectors/reviews/intake` blocks (07-VERIFICATION W4), so quote/review/capacity/brief/intake workflows return 404 or are gated off for them. `demo-venue` lives in `api/app/tests_data/packs/` and is not in the mounted `./businesses`. For the live E2E, create a gitignored `.e2e-businesses/` (copy of `businesses/*` plus `demo-venue`) and a one-off compose override `-f docker-compose.e2e.yml` that mounts it at `/srv/businesses:ro` for the `api` service (same target path overrides the earlier entry), then `POST /admin/tenants {"pack_slug":"demo-venue"}`. Do NOT copy demo-venue into `businesses/` (breaks the "git status businesses empty" gate and would add a tenant to the live image). Fallback if this is rejected: prove module workflows by CI check + `run_flows` equivalence and say so (D-09).

Code-node health caveat: the branch n8n logs repeated `Task ... rejected by Runner ... Offer expired` and `Database connection timed out` (after ~13 h uptime/host sleep). Code nodes run on task runners in 2.x; if headless runs hang, `--force-recreate n8n` first. [VERIFIED log lines; cause ASSUMED = host sleep]

## 10. Plan split (6 sequential plans, each <=10 files)

1. **API groundwork** (~9 files): `tenants.py` (owner resolver), `tenant_routes.py` + `main.py`, `tools.py` (tenant_id in payload + mailer fallback), `brief_routes.py` (404), `drafts.py` (`/sent`), `quotes.py` (`contact_email`), tests: `test_tenant_me.py`, extend `test_brief.py`, `test_drafts.py`/`test_quotes_api.py`, escalation fallback test. RED first each.
2. **Migrate existing workflows + compose** (~7): `inbound-message.json`, `followup-scheduler.json`, `escalation-alert.json`, delete `daily-report.json`, `docker-compose.yml` (`TENANT_API_KEYS` env, pin n8n tag, `./n8n:/srv/n8n:ro` on api), `.env.example`, README n8n section.
3. **CI check + admin fallback flip** (~5): `test_n8n_workflows.py`, `Makefile` (`check-n8n`), `admin.py` (`_write_tenant` -> 400), `test_admin.py`, `test_routes_scope.py`. CI lands before the new workflows so they are guarded as written.
4. **New workflows A** (~3): `quote-request.json`, `review-reply.json` (+ approved-sender lanes), update EXPECTED set in the test.
5. **New workflows B** (~3): `capacity-check.json`, `daily-brief.json`, `intake-event.json`.
6. **run_flows + proof** (~5): `scripts/run_flows.py`, `Makefile` (`run-flows`), `test_run_flows.py`, `docker-compose.e2e.yml` + `.gitignore` entry, plus a human-verify/automated task capturing the headless branch-stack run (commands in section 9) into the SUMMARY.

Wave rule: nothing in 4-5 should be written before 1 (they call `/tenant/me` and `/drafts/{id}/sent`).

## Common Pitfalls

1. **Loop dies on an empty branch** (verified). Use `alwaysOutputData` + gate + loop-back on every nullable node.
2. **`$env` blocked** when `N8N_BLOCK_ENV_ACCESS_IN_NODE` is unset in 2.x (verified). Keep the compose line; the CI test can assert it is `"false"` in `docker-compose.yml`.
3. **`.item` pairing errors after Code nodes**: use `.first()` with batchSize 1.
4. **`QuoteBody`/`ReviewIn`/`EventIn` are `extra="forbid"`**: sending `tenant_id` in the body 422s. Strip it in Normalize.
5. **Inbound body**: current Call agent sends `JSON.stringify($json)`; adding `tenant_id` to the normalized item would leak into the body. Build the body explicitly.
6. **Admin key left on a tenant-aware node** silently keeps working through the default fallback until plan 3 flips it; the CI check catches it first.
7. **Import-on-start does not delete**: removing `daily-report.json` leaves the old active workflow in an existing `n8ndata` volume (still sends to a hardcoded address with the admin key). Branch stack: `make g-reset` or remove it in the n8n UI; live stack: note in the SUMMARY. [ASSUMED no CLI delete]
8. **Escalation fallback in tests**: webhook-unset tests now exercise the mailer path; keep resolver returning None when `OWNER_EMAIL` is empty.
9. **Brief row written before mail** (section 6): gate on owner before `POST /daily-brief`.
10. **Execution data holds PII** (inbound messages, intake payloads): out of scope here; note for Phase 9 (`EXECUTIONS_DATA_PRUNE`, `EXECUTIONS_DATA_SAVE_ON_SUCCESS`).
11. **Pack bytes**: any edit under `businesses/<slug>/` (even a comment) changes `pack_hash` and fails `PINNED`; do not touch.
12. **Webhook trust**: tenant id in the request selects the key (Open Question 5).

## Code Examples

Header node (HTTP v4.2), single-item flow:
```json
{"parameters":{"method":"GET","url":"={{ $env.API_URL }}/tenant/me","sendHeaders":true,
 "headerParameters":{"parameters":[{"name":"X-API-Key","value":"={{ JSON.parse($env.TENANT_API_KEYS)[$('Normalize alert').first().json.tenant_id] }}"}]}},
 "name":"Tenant me","type":"n8n-nodes-base.httpRequest","typeVersion":4.2}
```
Loop wiring (connections): `Each tenant.main[1] -> With key`, last node `-> Each tenant`; `Each tenant.main[0]` empty. Verified shape: see the executed `loop.json` pattern in scratchpad `/private/tmp/claude-501/-Users-ervenderr-Projects-roofdeskai/0c064e05-2147-4d14-9df0-2574595a5952/scratchpad/wf/loopB.json` (throwaway, not committed).

Mail node (kept as is, only the expression changes):
`={{ JSON.stringify({From:{Email:'no-reply@roofdesk.test',Name:$('Tenant me').first().json.name},To:[{Email:$('Tenant me').first().json.owner_email}],Subject:...,Text:...}) }}`

## State of the Art

| Old | Current | Impact |
|---|---|---|
| n8n 1.x `$env` available by default | 2.x blocks by default; Code nodes always on task runners | explicit `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` kept; runner health matters |
| Per-workflow admin key + default tenant | tenant key from env map | this phase |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | HTTP v4.2 pass-through option shape (`neverError` + `fullResponse`, `$json.statusCode`) | 6 capacity/intake | respond node wiring differs; verify by import + curl in plan 4/5 |
| A2 | No n8n CLI to delete an imported workflow (stale `daily-report` on existing volumes) | 1, pitfall 7 | extra cleanup step, low |
| A3 | `saveDataSuccessExecution: none` workflow setting name | 6 intake | cosmetic; Phase 9 owns retention |
| A4 | `n8n execute` alongside a running server on one SQLite works | 9 | fall back to throwaway container |
| A5 | Stale Runner "offer expired" cause = host sleep | 9 | n8n restart needed more often |
| A6 | `/daily-brief/due` currently returns 200 empty rather than 500 | 5 | none; fix is 404 either way |

## Open Questions (RESOLVED)

VALIDATION.md is waived for this phase (the Validation Architecture section above plus per-task automated verify commands stand in for it).

1. RESOLVED: owner email = `pack.meta.owner_email or settings.owner_email` (env `OWNER_EMAIL`); roofing/dental pack YAML is NOT edited (deliberate deviation from D-05; keeps pack hash pins and byte-identical packs).
2. RESOLVED: admin fallback removal = hard 400 when no tenant on the three write routes; explicit admin key + `X-Tenant-Id` stays allowed.
3. RESOLVED: add `POST /drafts/{id}/sent` (approved -> sent) and optional `contact_email` on `QuoteBody` (excluded from the dedupe hash).
4. RESOLVED: keep the n8n booking confirmation node, neutralise its text (no business-specific wording; name from `/tenant/me`).
5. RESOLVED: defer a webhook shared secret; n8n port stays internal; document the risk in README and the SUMMARY.
6. RESOLVED: module E2E uses the gitignored `.e2e-businesses/` plus `docker-compose.e2e.yml` overlay; `demo-venue` is never copied into `businesses/`.
7. RESOLVED: workflow count = 3 tenant-aware existing + 2 untenanted allowlisted + 5 new = 10 files (daily-report retired); the ROADMAP/REQUIREMENTS wording ("6 existing", "11") is superseded and is not edited in this phase.
8. RESOLVED: pin `n8nio/n8n:2.18.5` in docker-compose.yml.
9. RESOLVED (A2): `n8n` 2.18.5 has no delete command; it does have `unpublish:workflow`. Stale `daily-report` on an existing `n8ndata` volume is unpublished via `n8n unpublish:workflow --id=daily-report` after stop/recreate; full removal is `make g-reset` (branch) or the n8n UI delete (live), documented.
10. RESOLVED (A6): `/daily-brief/due` with admin + nonexistent tenant id: record the actual pre-fix status in the RED test run; fix is 404 either way.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Docker | stack, throwaway n8n runs | yes | running | - |
| n8n image | all workflows | yes | 2.18.5 | - |
| Branch stack (db, api, mailpit, n8n) | E2E | yes | up (api ~1 h, n8n 13 h) | `make g-up` |
| mailpit API | evidence | yes | host 18025 | - |
| host pytest | CI check | no | - | run in api container |
| LLM for quote/review/booking | live E2E of LLM routes | not checked (Ollama on host) | - | fake `llm.chat` in pytest; W3 in Phase 7 already notes never run live |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 in the api container |
| Config file | none (conftest.py in `api/app`) |
| Quick run | `make g-test ARGS="app/test_n8n_workflows.py app/test_tenant_me.py -q"` |
| Full suite | `make g-test` |

### Phase Requirements -> Test Map
| Req | Behavior | Type | Command | Exists |
|-----|----------|------|---------|--------|
| WF-01 | tenant/me; workflows carry key; owner from API | unit + static | `app/test_tenant_me.py`, `app/test_n8n_workflows.py` | Wave 0 |
| WF-02 | draft sent transition, quote contact_email, workflows exist | unit + static; headless E2E | `app/test_drafts.py`, E2E commands | partial |
| WF-03 | due 404; admin-only tenants call | unit/static | `app/test_brief.py` | extend |
| WF-04 | flows through API, n8n off, escalation fallback | integration | `app/test_run_flows.py`, escalation test | Wave 0 |
| WF-05 | CI header check + negative mutants | static | `make check-n8n` | Wave 0 |

Sampling: per task the relevant file; per wave `make g-test`; gate: full suite plus `make g-eval-modules` unaffected; roofing eval is NOT required (no engine change) but `git status businesses` must be empty.
Wave 0 gaps: `test_tenant_me.py`, `test_n8n_workflows.py`, `test_run_flows.py`, escalation-fallback test, `./n8n:/srv/n8n:ro` mount.

## Security Domain

| ASVS | Applies | Control |
|---|---|---|
| V2/V3 Auth, keys | yes | per-tenant `X-API-Key` (sha256 at rest, Phase 6); admin key only for tenant listing; CI header check |
| V4 Access control | yes | `/tenant/me` via `require_tenant`; admin write routes require explicit tenant; cross-tenant leak test for `/tenant/me` and `/drafts/{id}/sent` (A cannot mark B's draft: `_decide` filters tenant) |
| V5 Input validation | yes | pydantic `extra="forbid"` models; strip `tenant_id`; UUID regex in Normalize; `contact_email` length/pattern |
| V6 Crypto | no new | none hand-rolled |
| V7 Logging | yes | do not log `TENANT_API_KEYS`, payloads; fallback mail contains link only, no transcript/PII |

Threats: key in committed JSON (CI scan), webhook choosing another tenant (Open Q5), admin key on tenant data (CI), SSRF none new, unapproved send (only `status=approved`, API state machine), duplicate send (at-least-once documented).

## Sources

### Primary (HIGH)
- Executed in throwaway containers of `n8nio/n8n:2.18.5`: env access allowed/blocked, `$env` in Code and expression, SplitInBatches key pairing, empty-branch loop termination and `alwaysOutputData` fix, `n8n execute` needing a Manual Trigger.
- Repo files read: `n8n/workflows/*.json`, `docker-compose*.yml`, `.env.example`, `Makefile`, `api/app/{admin,auth,tenant_admin,main,mailer,config,brief_routes,quotes,reviews_routes,capacity_routes,intake_event_routes,drafts,tenants,tools,agent,triage,pack,db,conftest}.py`, `db/migrations/007`, Phase 6/7 SUMMARY/VERIFICATION, spec workflow catalog.
### Secondary (MEDIUM)
- n8n 2.0 breaking changes (env access default true, task runners default): https://n8n.nodejs.cn/2-0-breaking-changes (mirror), https://www.infralovers.com/blog/2025-12-12-n8n-2-0-hardening-release/ ; consistent with the executed behaviour.

## Metadata

**Confidence breakdown:** Standard stack HIGH (no new deps); architecture HIGH (patterns executed); pitfalls HIGH; HTTP pass-through option names MEDIUM-LOW (A1).
**Research date:** 2026-11-04. **Valid until:** 2026-12-04 (re-check if the n8n tag is not pinned).

## Project Constraints (from CLAUDE.md)
- n8n triggers and sends; all decisions in FastAPI; platform must run without n8n.
- Regression gate: roofing stays 94/96 (no engine change here; do not edit `businesses/`).
- Simplicity: smallest change per step; work on branch `roofdesk-global`; do not break roofdeskai.com.
- Do not add Alembic/new libraries; numbered SQL migrations only (none needed this phase).
- Global rules: no secrets in code, `.env.example` placeholders only; failing test first; validate at boundaries; commit format `type: description`.
