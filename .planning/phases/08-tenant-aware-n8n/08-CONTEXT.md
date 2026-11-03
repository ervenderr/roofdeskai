# Phase 8: Tenant-Aware n8n - Context

**Gathered:** 2026-11-04 (auto mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver WF-01..WF-05: tenant-aware n8n workflows, new module workflows, API-driven scheduling over tenants, API-only operation (n8n off), and a CI check on the key header. n8n only triggers and sends; all decisions stay in FastAPI. No new engine logic (Phase 7 modules are called as-is), no supplier-order workflow (cut), no SOP generation (Phase 9).
</domain>

<decisions>
## Implementation Decisions

### Which workflows are tenant-aware
- **D-01:** Tenant-aware (send `X-API-Key`, never the admin key for tenant data): `inbound-message`, `followup-scheduler`, `escalation-alert`. `daily-report` is replaced by the new `daily-brief` (retire its JSON; keep `/metrics` endpoint). `outreach-flow` and `error-handler` are RoofDesk's own untenanted tooling (TEN-06): they stay on the admin key / no API call and are listed in an explicit allowlist in the CI check, not silently skipped.
- **D-02:** New workflows (5): `quote-request`, `review-reply`, `capacity-check`, `daily-brief`, `intake-event`, all calling Phase 7 endpoints with a tenant key. Total = 3 existing tenant-aware + 2 untenanted + 5 new (supplier-order is cut-first, deferred). Workflow JSON lives in `n8n/workflows/`, imported by the existing compose entrypoint.
- **D-03:** Existing `inbound-message` and `followup-scheduler` stop relying on the admin key + default-tenant fallback (Phase 6 deviation D-06): they send the tenant key, and the API-side admin `X-Tenant-Id`/default fallback is then removed or restricted so admin-key calls without a tenant fail clearly (planner decides removal vs hard 400; roofing flows must keep working).

### Tenant keys in n8n
- **D-04:** Tenant keys never committed. Keys are issued with the Phase 6 admin endpoints and provided to n8n through an env var map (`TENANT_API_KEYS` JSON `{tenant_id: key}`) read in Code/expression nodes (`$env`), documented in `.env.example` with placeholders only. Rotating a key = updating the env. (Per-tenant n8n Header Auth credentials are not selectable dynamically by tenant id; env map is the simplest working option.) The admin key is used only for `GET /admin/tenants` and tenant-listing.

### Owner address and tenant config from the API
- **D-05:** Add `GET /tenant/me` (tenant key) returning `{tenant_id, slug, name, owner_email, timezone, locale, enabled_modules}` from the pack/tenants data; workflows take the owner/notification address from this response, not from hardcoded values or env. If the pack lacks an owner email field, add it to pack.yaml models (optional, validated) and set it for roofing/dental as placeholder/demo addresses - flag if this changes pack hashes (pinned hash test must be updated deliberately in the same commit, and the prompt render must stay byte-identical).

### Scheduling
- **D-06:** Scheduled workflows (`followup-scheduler`, `daily-brief`, `capacity-check` nightly) run one trigger, call `GET /admin/tenants` (admin key), then loop per tenant (Split In Batches) using that tenant's key. The API decides who is due: `POST /daily-brief/due` for briefs; follow-up and capacity use the existing due/range endpoints. n8n never computes tenant-local time. Fix the Phase 7 warning: `/daily-brief/due` with admin key + nonexistent tenant id must return 404 not 500.

### Platform runs without n8n (WF-04)
- **D-07:** Add `scripts/run_flows.py` (and `make run-flows`) that performs the same API call sequences as the workflows (list tenants, per-tenant due/draft/send via the API, mail through the existing mailer) with no n8n. A pytest runs it against the test client/branch API with n8n absent and asserts a booking, escalation notification, follow-up and brief complete. The API's escalation notifier must not require n8n: if `ESCALATION_WEBHOOK_URL` is unset or fails, it logs and falls back to direct mail via the existing mailer (planner confirms how escalation delivery works today).

### CI check (WF-05)
- **D-08:** A pytest (`test_n8n_workflows.py`) parses every `n8n/workflows/*.json`: every HTTP Request node whose URL targets `$env.API_URL` must carry an `X-API-Key` header (or, for the allowlisted untenanted workflows, `X-Admin-Key`), listed explicitly; every workflow referenced in the catalog exists; no committed secrets (no `rd_live_` strings). Also runs via `make check-n8n`. No GitHub Actions needed (no workflows dir exists; wiring CI itself is out of scope, record as note).

### End-to-end proof
- **D-09:** Verify new workflows in the branch compose stack (n8n + mailpit) by importing, triggering webhooks/manual executions, and checking mailpit/API state; evidence captured in the SUMMARY. If n8n cannot be driven headlessly in this environment, fall back to schema/CI checks plus `run_flows.py` equivalence tests and say so explicitly.

### Claude's Discretion
- Exact webhook paths, node layout, Code-node snippets, batching sizes, email templates, whether `daily-report.json` is deleted or left disabled, `/tenant/me` field details, plan split (expect ~5-6 plans).

### Open items carried in
- Confirm "call 144" Swiss emergency number; deploy needs `PUBLIC_DEMO_TENANT_ID` and `APP_DATABASE_URL`; n8n Sustainable Use License decision still open (research flag, do not change stack).
</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` Phase 8 — goal and 5 success criteria; `.planning/REQUIREMENTS.md` WF-01..WF-05
- `/Users/ervenderr/Downloads/RoofDesk Global Platform Spec.md` — workflow catalog (lines ~91-110)
- `.planning/research/SUMMARY.md` and STACK notes on n8n (no community nodes, key header on every HTTP node, `GET /admin/tenants` loop, API decides due-ness)
- `.planning/phases/06-per-tenant-keys-and-rls-enforcement/06-04-SUMMARY.md` — admin X-Tenant-Id fallback to remove; `06-VERIFICATION.md`
- `.planning/phases/07-engine-modules-and-connectors/07-VERIFICATION.md` and 07-0x summaries — endpoints to call
- `n8n/workflows/*.json`, `docker-compose.yml` / `docker-compose.global.yml` (n8n service, import entrypoint, mailpit)
- `api/app/admin.py`, `auth.py`, `tenant_admin.py`, `brief_routes.py`, `quotes.py`, `reviews_routes.py`, `capacity_routes.py`, `intake_event_routes.py`, `mailer.py`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 6 workflow JSONs with `X-Admin-Key` headers and mailpit send nodes; `mailer.py`; tenant admin endpoints; `/daily-brief/due`; `require_scope`.

### Established Patterns
- n8n only triggers and sends; JSON exported to `n8n/workflows/` and imported by compose entrypoint (`n8n import:workflow` + `publish:workflow`).

### Integration Points
- Escalation currently POSTs to an n8n webhook (`ESCALATION_WEBHOOK_URL`); inbound-message calls `/webhooks/inbound` with admin key (default tenant).
</code_context>

<specifics>
No specific requirements beyond the roadmap criteria.
</specifics>

<deferred>
## Deferred Ideas

- supplier-order workflow (v2); appointment reminders, knowledge-gap loop, nightly eval run (v2 backlog)
- GitHub Actions wiring for the CI check; per-tenant n8n credentials UI; n8n licence decision
</deferred>

---

*Phase: 8-Tenant-Aware n8n*
*Context gathered: 2026-11-04*
