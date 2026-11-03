# Phase 6: Per-Tenant Keys and RLS Enforcement - Context

**Gathered:** 2026-11-04 (auto mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Tenants are isolated by credential and by the database. Deliver SEC-01..SEC-05: hashed per-tenant API keys (issue/rotate/revoke), tenant derived from the credential, enforced Postgres RLS (FORCE, non-owner app role, column default dropped), a cross-tenant leak test on an RLS-enabled DB, and a super-admin scope separate from tenant keys. No new engine modules, no n8n edits (Phase 8 adds the key header to workflows).
</domain>

<decisions>
## Implementation Decisions

### Credential and key format
- **D-01:** Tenant keys are `rd_live_` + `secrets.token_urlsafe(32)`; only `sha256` hex is stored in `tenant_api_keys(id, tenant_id, key_hash, label, created_at, revoked_at)`; shown once on issue; compared with `hmac.compare_digest` on the hash. Header: `X-API-Key`.
- **D-02:** Rotate = issue a new key and set `revoked_at` on the old one in one transaction (no grace window; operator can issue a second key first if overlap is wanted). Revoked or unknown key → 401 with a generic body.
- **D-03:** Key lookup runs in `db.system()` (keys table is not tenant-scoped); the resolved tenant id is then used for `db.tx(tenant_id)`.

### Tenant resolution
- **D-04:** One FastAPI dependency `require_tenant` returns the tenant id from `X-API-Key`. Tenant ids in request bodies/queries are ignored (schemas do not accept them). Missing key → 401.
- **D-05:** Public demo: `/chat` must keep working on roofdeskai.com without a key. Decision: optional env `PUBLIC_DEMO_TENANT_ID`; when set, `/chat` (only) falls back to it if no key is sent; when unset, `/chat` returns 401. Default unset in code/compose for the branch; deploy sets it. Flag to user: this is the one keyless path.
- **D-06:** `settings.default_tenant_id` column default and the config constant are removed from tenant data paths. Remaining uses (admin.py webhooks/followups, `tools.py`, etc.) take the tenant from `require_tenant`.

### Admin scope
- **D-07:** `X-Admin-Key` stays as the super-admin scope: tenant CRUD, key issue/rotate/revoke, `GET /admin/tenants`, cross-tenant metrics. Tenant keys cannot call these (403/401). Existing dashboard/n8n read endpoints (`/leads`, `/conversations`, `/metrics`, escalations, followups, inbound webhook) become tenant-scoped under a tenant key; super-admin versions of metrics aggregate across tenants. Dashboard keeps using the admin key (cross-tenant), unchanged behaviour for the demo.
- **D-08:** Outbound/outreach/replies/pilot/intake (RoofDesk's own sales funnel) stay untenanted and on the admin key (TEN-06).

### RLS enforcement
- **D-09:** New migration `005_rls.sql`: create non-superuser, non-owner role `app_rw` (NOLOGIN→LOGIN with password from env); migrator/owner keeps DDL. `ENABLE` + `FORCE ROW LEVEL SECURITY` on every tenant table (leads, conversations, messages/events, slots, appointments, FAQ rows, agent_events, llm_calls where tenant-scoped); policy `USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`; drop the `tenant_id` column DEFAULT. Matches the Phase 2 scratch-DB proof in `test_rls_proof.py`.
- **D-10:** `db.system()` (cross-tenant/system context) must still work under RLS: use a separate `system` connection role/policy path (e.g. second engine as the owner role or a `BYPASSRLS` system role) used only by bootstrap, key lookup, tenant listing, super-admin endpoints. Planner picks the simplest of the two; no raw `engine.begin()` in tenant code.
- **D-11:** Compose: API connects as `app_rw`; migrations/bootstrap connect as the owner. Pytest runs against an RLS-enabled DB so every existing test exercises RLS (fix tests, don't weaken policies).

### Leak test and evals
- **D-12:** SEC-04 leak test (pytest, two tenants, RLS on): chat, FAQ retrieval, slots, metrics, conversations and admin lists each return only own rows; no-key and wrong-key → 401; no tenant context query → 0 rows; body tenant id ignored.
- **D-13:** Regression gate: roofing 94/96 same two failures and dental 43/43 must still pass after RLS (eval harness runs through the API/agent paths with explicit tenant; planner decides whether the runner uses a tenant context directly).

### Claude's Discretion
- Exact migration numbering/structure beyond `005_rls.sql`; whether `tenant_api_keys` already needs creation or exists (check migrations); admin endpoint paths for key management; system-role mechanism (D-10).

### Open items carried in
- Intermittent pytest failure after evals (cause unknown, twice): capture the failing test id; RLS test DB must rule out leftover-state cause.
- Confirm "call 144" emergency number with user (Phase 5 carry-over).
</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` Phase 6 — goal and 5 success criteria
- `.planning/REQUIREMENTS.md` SEC-01..SEC-05
- `.planning/research/SUMMARY.md` — RLS owner/superuser pitfall, per-tenant keys (sha256/hmac), admin key separate scope
- `.planning/PROJECT.md` — "Public multi-tenant exposure before per-tenant keys + RLS" out of scope
- `db/migrations/001_tenants.sql`..`004_agent_events.sql` — existing schema, `schema_migrations`
- `api/app/db.py` (`tx`, `system`), `api/app/admin.py` (`require_admin`), `api/app/main.py` (`/chat`), `api/app/config.py` (`default_tenant_id`)
- `api/app/test_rls_proof.py`, `api/app/test_isolation.py`, `api/app/test_tenancy.py` — existing proofs to extend
- `docker-compose.yml`, `docker-compose.global.yml` — DB role/URL wiring
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.tx(tenant_id)` sets transaction-local `app.tenant_id`; `db.system()` for cross-tenant. RLS policies already proven on a scratch DB.
- `admin.require_admin` + `hmac.compare_digest` pattern to copy for keys.
- `tenants.ensure_tenant`, `test_isolation.py` two-tenant fixtures.

### Established Patterns
- Numbered SQL migrations applied from `bootstrap.py` under an advisory lock; plain SQL, no Alembic.
- App currently connects as compose superuser `leadpilot` (RLS bypassed) — the core thing this phase changes.

### Integration Points
- Every route in `main.py`/`admin.py` gets `require_tenant` or `require_admin`.
- `settings.default_tenant_id` call sites in admin.py/tools/agent paths.
- n8n workflows currently send only the admin key; Phase 8 updates them, so Phase 6 must keep admin-key access to the existing n8n-called endpoints working.
</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the roadmap criteria.
</specifics>

<deferred>
## Deferred Ideas

- Per-key scopes/rate limits per tenant, key expiry, audit log of key use (not in SEC-01..05).
- n8n credential per tenant (Phase 8).
- Clerk login (v2).
</deferred>

---

*Phase: 6-Per-Tenant Keys and RLS Enforcement*
*Context gathered: 2026-11-04*
