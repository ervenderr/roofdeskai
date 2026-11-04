# Phase 7: Engine Modules and Connectors - Context

**Gathered:** 2026-11-04 (auto mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver MOD-01..MOD-07 and EVAL-05: quote builder, capacity checker, connector layer (mocks), daily brief, review responder, `intake_event` webhook, each pure/deterministic where it computes anything, each with its own deterministic eval set. All run through the API under tenant keys + RLS (Phase 6). No n8n workflow edits (Phase 8), no MCP wrapper, no Anthropic provider, no real third pack (Phase 10), no docs/SOP generation (Phase 9).
</domain>

<decisions>
## Implementation Decisions

### Pack extensions (shared)
- **D-01:** Add optional pack files `services.yaml`, `capacity.yaml`, `connectors.yaml`, plus optional `reviews:`/`intake:` blocks, loaded by the existing Pydantic loader (`extra="forbid"`, `PackError` naming file+field, hash includes them). Absent file = module disabled for that tenant (endpoint returns 404 "module not enabled"). Roofing and dental packs get no new files (roofing agent keeps refusing chat prices; 94/96 untouched).
- **D-02:** Module tests/evals need a pack that uses them. Create a small synthetic fixture pack `api/app/tests_data/packs/demo-venue/` (services with group/corporate rules, rota/capacity, connectors, intake mapping). Phase 10 promotes the idea to the real third pack; do not build it here.
- **D-03:** Engine modules live in `api/app/engine/` as pure functions of `(pack, input)` returning frozen dataclasses/Pydantic models; DB access and routes stay in thin route modules. No `settings.default_tenant_id`; tenant always explicit via `require_tenant`.

### Quote builder (MOD-01, MOD-02)
- **D-04:** `Decimal` only; services have `id`, `name`, `unit` (per_person/flat/per_hour), `price`, optional `min_qty`, `add_ons`, and `rules` (group tier discounts, corporate surcharge as percentages/fixed). Total quantized once at the end; currency from the pack.
- **D-05:** Missing price, unknown service, qty below min, or a rule that cannot be evaluated returns a typed `NeedsHuman(reason, missing=[...])`; never a guess. Request input is structured (`service_id`, `qty`, `add_on_ids`, `customer_type`); the LLM may extract fields from an email but only validated structured input reaches the builder.
- **D-06:** New tenant-scoped `drafts` table (migration 007, RLS + grants like Phase 6): `id, tenant_id, kind (quote|review_reply), status (pending|approved|rejected|needs_human|sent), payload jsonb, input_hash, created_at, decided_at`. Quote draft payload stores computed line items + total + model-written email text. Approve/reject endpoints. The existing outreach approval queue stays untenanted and untouched.
- **D-07:** Quote email text is validated against the computed quote (every number in the text must equal the quote total/line prices; no other currency amounts) instead of the roofing `_CLAIM_RE` price-claim regex; failure → regenerate once → `needs_human`. Quote drafts are never auto-sent.

### Capacity checker (MOD-03)
- **D-08:** `capacity.yaml` defines shifts (name, weekday/time window in tenant tz) with `min_staff`, `max_covers_per_staff` (or resource capacity), and rota (staff per shift). Checker compares bookings (appointments/bookings table or the bookings connector) per shift and returns flags `over_capacity|understaffed|under_utilised` with a stable `flag_key`.
- **D-09:** Flags persisted in `capacity_flags` (tenant-scoped, RLS): unique `(tenant_id, flag_key)` + `input_hash`; re-running with unchanged inputs creates nothing new (dedupe); changed inputs update and set `reflagged_at` and return as "re-flagged". Resolved flags clear when inputs fix them.
- **D-10:** All time math in `zoneinfo` tenant tz with UTC storage; tests cover spring-forward and fall-back days for America/Denver and Europe/Zurich.

### Connector layer (MOD-04, MOD-05)
- **D-11:** One `Connector` Protocol (`name`, `fetch(tenant, day) -> ConnectorResult`) with mock adapters `sheet`, `accounting`, `bookings`, `ads`. Mock data is deterministic (seeded by tenant slug + date), and every result carries `source="mock"`; any output rendering it labels it "(mock data)". A connector may raise/return `unavailable`; the brief shows "source unavailable" explicitly, never omits silently. Adapter classes are plain, MCP-wrappable later (EXT-02).
- **D-12:** `connectors.yaml` lists enabled sources per tenant. Daily brief (`POST /daily-brief` + `POST /daily-brief/due`): merges connector data into a one-page text/HTML summary, in tenant-local time; `due` returns tenants whose local hour matches the configured send hour and not yet sent that day (state in a `brief_runs` table, tenant-scoped). Disagreement check: the same metric reported by two sources (e.g. bookings count in `bookings` vs `sheet`) differing beyond tolerance is flagged with both numbers. Brief numbers are code-computed; any prose is templated, no LLM required (optional LLM polish out of scope).

### Review responder (MOD-06)
- **D-13:** `POST /reviews/draft` takes `{review_text, rating, platform}`; LLM drafts in the pack tone (`reviews:` block: tone, signature, forbidden topics). Deterministic post-check `check_reply(text, pack)` blocks: refund/discount/compensation offers, fault admission, unknown-fact claims (reuse grounding-style check against pack facts), and PII (email/phone/address patterns, plus health-privacy language for dental: no confirming someone was a patient). Fail → regenerate once → status `needs_human`; pass → `pending` draft. Never auto-posted; no sentiment gating (all ratings treated the same path).

### intake_event (MOD-07)
- **D-14:** `POST /intake_event` (name chosen to avoid the untenanted `/intake`) with tenant key. Pack `intake:` block maps source payload fields (`waiver|checkin|result`) via simple dotted-path mapping to `person_key` (email/phone/external id), name, and event fields. Table `intake_people` unique `(tenant_id, person_key)` with `waiver_at/checkin_at/result jsonb`; repeated events upsert, one row per person; processed twice → same single record (idempotent). Unmapped/invalid payload → 422 naming the field; no PII in logs (log ids only).

### Evals (EVAL-05)
- **D-15:** Each module gets a deterministic eval set under `evals/modules/<module>/*.yaml` and a runner `python -m evals.modules [--module X]` that needs no LLM (review responder evals feed fixed drafts to the post-check; quote/capacity/brief/intake are pure). Runs in pytest too. Existing 94/96 roofing and 43/43 dental gates run once at the end of the phase as regression; module eval sets must all pass (they are deterministic, so 100%).

### Claude's Discretion
- File/module naming under `api/app/engine/`, exact table column details, mock data shapes, HTML vs text brief format, endpoint path names beyond those above, plan split (expect ~7-8 sequential plans: pack extension + drafts/migrations, quote, capacity, connectors+brief, review responder, intake_event, module evals + gates).

### Open items carried in
- Confirm "call 144" Swiss emergency number (Phase 5).
- Deploy needs `PUBLIC_DEMO_TENANT_ID` and `APP_DATABASE_URL` (Phase 6); new tables in this phase must follow the Phase 6 RLS/grant pattern (migration 007+; `assert_rls_enforced` coverage check should include new tables).
</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` Phase 7 — goal and 6 success criteria
- `.planning/REQUIREMENTS.md` MOD-01..MOD-07, EVAL-05
- `/Users/ervenderr/Downloads/RoofDesk Global Platform Spec.md` — "New engine modules" table (lines ~80-90), workflow catalog, coverage-of-job-post table
- `.planning/research/SUMMARY.md` — module design pitfalls (Decimal, DST, idempotent re-flag, draft-only guardrails, mock labelling)
- `.planning/phases/06-per-tenant-keys-and-rls-enforcement/06-CONTEXT.md` and `06-02-SUMMARY.md` — RLS/grant/migration pattern for new tables
- `api/app/pack.py` (loader/models), `api/app/policy.py` (grounding/escalation checks to reuse), `api/app/auth.py` (`require_tenant`), `api/app/db.py` (`tx`), `db/migrations/005_rls.sql`
- `api/app/outreach.py` / `outreach_routes.py` — existing (untenanted) approval-queue pattern for reference only
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Pack loader with `extra="forbid"`, hash-keyed `get_pack`; `Decimal` already chosen in stack research.
- `policy.py` grounding/claim checks, `llm.chat` provider chain, `record_event`/`agent_events` for audit.
- Phase 6 auth + RLS migration template; `test_leak.py` fixtures for two-tenant tests.

### Established Patterns
- Pure functions + thin routes; typed `NeedsHuman`-style outcomes (model proposes, code decides); per-pack eval files; numbered SQL migrations with explicit GRANTs and FORCE RLS.

### Integration Points
- New routers included in `main.py` under `require_tenant`; new tables added to RLS catalog tests (`test_rls_proof`, `test_leak`); roofing/dental prompts and scenarios must not change.
</code_context>

<specifics>
## Specific Ideas

Quotes may show computed prices only for packs that ship `services.yaml`; the roofing chat agent keeps refusing prices.
</specifics>

<deferred>
## Deferred Ideas

- n8n workflows for these modules and the `/admin/tenants`-driven scheduling loop (Phase 8)
- MCP exposure of connectors, Anthropic provider, real venue pack (Phase 10)
- Supplier-order workflow (v2, cut first); real connectors/write actions (v2)
- Generated SOPs and data map for these modules (Phase 9)
</deferred>

---

*Phase: 7-Engine Modules and Connectors*
*Context gathered: 2026-11-04*
