# Phase 6: Per-Tenant Keys and RLS Enforcement - Research

**Researched:** 2026-11-04
**Domain:** Postgres RLS enforcement (FORCE, non-owner role), hashed per-tenant API keys, FastAPI auth dependencies, test/eval harness under RLS
**Confidence:** HIGH on code inventory (read directly); MEDIUM on Postgres behaviours (training knowledge plus the existing `test_rls_proof.py`, nothing re-fetched this session); MEDIUM on the pytest-failure cause (static analysis only, tests not run per instructions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tenant keys are `rd_live_` + `secrets.token_urlsafe(32)`; only `sha256` hex is stored in `tenant_api_keys(id, tenant_id, key_hash, label, created_at, revoked_at)`; shown once on issue; compared with `hmac.compare_digest` on the hash. Header: `X-API-Key`.
- **D-02:** Rotate = issue a new key and set `revoked_at` on the old one in one transaction (no grace window; operator can issue a second key first if overlap is wanted). Revoked or unknown key -> 401 with a generic body.
- **D-03:** Key lookup runs in `db.system()` (keys table is not tenant-scoped); the resolved tenant id is then used for `db.tx(tenant_id)`.
- **D-04:** One FastAPI dependency `require_tenant` returns the tenant id from `X-API-Key`. Tenant ids in request bodies/queries are ignored (schemas do not accept them). Missing key -> 401.
- **D-05:** Public demo: `/chat` must keep working on roofdeskai.com without a key. Optional env `PUBLIC_DEMO_TENANT_ID`; when set, `/chat` (only) falls back to it if no key is sent; when unset, `/chat` returns 401. Default unset in code/compose for the branch; deploy sets it. Flag to user: this is the one keyless path.
- **D-06:** `settings.default_tenant_id` column default and the config constant are removed from tenant data paths. Remaining uses (admin.py webhooks/followups, `tools.py`, etc.) take the tenant from `require_tenant`.
- **D-07:** `X-Admin-Key` stays as the super-admin scope: tenant CRUD, key issue/rotate/revoke, `GET /admin/tenants`, cross-tenant metrics. Tenant keys cannot call these (403/401). Existing dashboard/n8n read endpoints (`/leads`, `/conversations`, `/metrics`, escalations, followups, inbound webhook) become tenant-scoped under a tenant key; super-admin versions of metrics aggregate across tenants. Dashboard keeps using the admin key (cross-tenant), unchanged behaviour for the demo.
- **D-08:** Outbound/outreach/replies/pilot/intake (RoofDesk's own sales funnel) stay untenanted and on the admin key (TEN-06).
- **D-09:** New migration `005_rls.sql`: create non-superuser, non-owner role `app_rw` (NOLOGIN->LOGIN with password from env); migrator/owner keeps DDL. `ENABLE` + `FORCE ROW LEVEL SECURITY` on every tenant table (leads, conversations, messages/events, slots, appointments, FAQ rows, agent_events, llm_calls where tenant-scoped); policy `USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`; drop the `tenant_id` column DEFAULT. Matches the Phase 2 scratch-DB proof in `test_rls_proof.py`.
- **D-10:** `db.system()` (cross-tenant/system context) must still work under RLS: use a separate `system` connection role/policy path (e.g. second engine as the owner role or a `BYPASSRLS` system role) used only by bootstrap, key lookup, tenant listing, super-admin endpoints. Planner picks the simplest of the two; no raw `engine.begin()` in tenant code.
- **D-11:** Compose: API connects as `app_rw`; migrations/bootstrap connect as the owner. Pytest runs against an RLS-enabled DB so every existing test exercises RLS (fix tests, don't weaken policies).
- **D-12:** SEC-04 leak test (pytest, two tenants, RLS on): chat, FAQ retrieval, slots, metrics, conversations and admin lists each return only own rows; no-key and wrong-key -> 401; no tenant context query -> 0 rows; body tenant id ignored.
- **D-13:** Regression gate: roofing 94/96 same two failures and dental 43/43 must still pass after RLS (eval harness runs through the API/agent paths with explicit tenant; planner decides whether the runner uses a tenant context directly).

### Claude's Discretion
Exact migration numbering/structure beyond `005_rls.sql`; whether `tenant_api_keys` already needs creation or exists (check migrations); admin endpoint paths for key management; system-role mechanism (D-10).

### Deferred Ideas (OUT OF SCOPE)
Per-key scopes/rate limits per tenant, key expiry, audit log of key use; n8n credential per tenant (Phase 8); Clerk login (v2).

Open items carried in: intermittent pytest failure after evals (find cause); confirm "call 144" emergency number with user (Phase 5 carry-over, not a research item).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | Issue/rotate/revoke per-tenant keys, hashed, shown once | S4 (new table, migration 006), S5 (endpoints), Code Examples |
| SEC-02 | Tenant from credential, never body; no key -> 401 | S5 (`require_scope`, `require_tenant`, demo fallback) |
| SEC-03 | RLS FORCE, non-owner app role, default dropped | S2, S3 (role design, policies SQL) |
| SEC-04 | Leak test on RLS-enabled DB | S7 |
| SEC-05 | Admin endpoints on separate super-admin scope | S5 endpoint table |
</phase_requirements>

## Summary

The tenant-aware plumbing is already in place: every tenant data path goes through `db.tx(tenant_id)` (transaction-local `set_config`), and `db.system()` marks untenanted work. The phase is therefore mostly (a) swapping which Postgres role those two helpers connect as, (b) a migration (role, grants, FORCE RLS, policies, drop DEFAULTs), (c) removing the silent `tenant_id or default_tenant_id` fallbacks, (d) a new auth module, and (e) fixing tests that insert rows without `tenant_id` or rely on a defaulted tenant.

Simplest role design: **keep `engine` (DATABASE_URL, compose superuser `leadpilot`) as the system/owner engine, and add `app_engine` (new `APP_DATABASE_URL`, role `app_rw`) as the default for `tx()`**. A superuser bypasses RLS even under FORCE, so `system()`, bootstrap, migrations, conftest cleanup and ~27 raw `engine.begin()` call sites in the untouched outreach funnel need zero edits. A non-superuser owner would be subject to FORCE RLS, so a hosted deploy whose migrator is not superuser needs `ALTER ROLE <owner> BYPASSRLS` run once by a superuser (the startup check below detects this).

The intermittent post-eval pytest failure is most likely `test_agent.py::test_slots_are_topped_up_when_the_calendar_runs_short`: its `dupes` query groups `slots` by `start_time` across ALL tenants. After a dental eval (non-`test-` tenant, slot hours overlap roofing's UTC hours in some DST periods) or after any leftover `test-%` tenant using the roofing calendar, two tenants hold the same instant and the assertion `dupes == 0` fails. The next pytest run passes because `conftest` deletes all non-default-tenant slots at session end. Fix is a one-line scope of that query. [ASSUMED: from static reading; confirm by capturing the failing test id (see S6)]

**Primary recommendation:** Two migrations, `005_rls.sql` (role, explicit grants, FORCE RLS + policies on 11 tables, drop 9 defaults) and `006_tenant_api_keys.sql`; new `api/app/auth.py`; `db.py` gets `app_engine`, `tx()` requires a tenant; every tenant-or-admin route takes one `require_scope` dependency and passes `_tenant=scope.tenant_id` to the existing `_rows()` helper, which already branches tenant vs system.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Key issue/rotate/revoke, hash storage | API / Backend | Database | Admin-scope endpoints, hash-only table |
| Credential -> tenant resolution | API / Backend (FastAPI dependency) | Database (system lookup) | Decision in FastAPI per CLAUDE.md architecture |
| Row isolation | Database (RLS) | API (always sets context) | Backstop against a forgotten `WHERE tenant_id` |
| Cross-tenant admin reads | API (admin scope) | Database (owner/superuser engine) | Only the system engine can see all rows |
| Public demo chat fallback | API / Backend | -- | Env-gated single keyless path |
| n8n/dashboard callers | n8n / Next.js server | API | Keep sending `X-Admin-Key` until Phase 8 |

## Standard Stack

No new packages. Everything is stdlib plus what is installed (`api/requirements.txt`: fastapi 0.115, sqlalchemy 2, psycopg 3.2, pydantic 2, pytest 8, httpx 0.27). [VERIFIED: api/requirements.txt]

| Need | Use | Note |
|------|-----|------|
| Key generation | `secrets.token_urlsafe(32)` with `rd_live_` prefix | per D-01 |
| Hash | `hashlib.sha256(key.encode()).hexdigest()` | fast hash is correct for 256-bit random secrets |
| Compare | `hmac.compare_digest` | already used in `admin.py` |
| RLS | Postgres built in | proven in `test_rls_proof.py` |

**Package Legitimacy Audit:** no external packages installed; slopcheck not needed. Packages removed: none. Flagged: none.

## Architecture Patterns

### Request flow

```
n8n / dashboard --X-Admin-Key--+
tenant client  ---X-API-Key----+--> FastAPI dependency require_scope / require_tenant
roofdeskai.com --(no key)------+        |  key -> sha256 -> system(): tenant_api_keys (revoked_at IS NULL)
   /chat only, if PUBLIC_DEMO_TENANT_ID |  admin key -> Scope(None) (+ optional X-Tenant-Id)
                                        v
                         Scope(tenant_id | None)
                          |                         |
              tenant_id set                   tenant_id None (admin only)
        tx(tenant_id) on app_engine        system() on engine (owner/superuser)
        role app_rw, RLS FORCE             bypasses RLS: cross-tenant, bootstrap, keys, outreach
        set_config('app.tenant_id', t, true)
```

### Recommended structure
```
api/app/auth.py            # require_admin (moved), Scope, require_scope, require_tenant, issue/rotate/revoke, hash
api/app/admin.py           # routes take scope; imports require_admin from auth (re-export keeps outreach_routes/triage imports working)
api/app/tenant_admin.py    # (or inside admin.py) GET/POST /admin/tenants, key endpoints; under require_admin only
db/migrations/005_rls.sql
db/migrations/006_tenant_api_keys.sql
```

### Pattern: `_rows` already does the branching
`admin._rows(sql, _tenant=X)` runs `tx(X)` if X else `system()`. Passing `scope.tenant_id` makes each read endpoint tenant-scoped under a tenant key (RLS does the filtering, SQL unchanged) and cross-tenant under the admin key. No per-query rewriting.

### Anti-patterns
- **`ALTER DEFAULT PRIVILEGES ... TO app_rw`** in 005: it would auto-grant `tenant_api_keys` (006) and every later table to `app_rw`. Use explicit per-table GRANTs; add a catalog test.
- **Falling back to `settings.default_tenant_id` when a tenant is missing.** That is the bug RLS is meant to catch; `tx(None)` must raise.
- **Honouring `X-Tenant-Id` for tenant keys.** Only accepted together with a valid admin key.

## S1. Inventory (all code read directly) [VERIFIED: codebase grep]

### Tenant tables (have `tenant_id`)
leads, conversations, messages, slots, appointments, faq_chunks, tool_calls, escalations, events (all `NOT NULL DEFAULT '0000...0001'`, 002), llm_calls (nullable, no default; NULL = outreach rows, 002), agent_events (`NOT NULL`, no default, 004). Total 11 for RLS. `tenants` is the directory (no `tenant_id`). Untenanted (no policy, no `app_rw` grant): campaigns, prospects, outreach_messages, suppressions, prospect_events, scrape_runs, eval_runs, eval_results, schema_migrations, tenants, and the new tenant_api_keys.

### Raw `engine` call sites (non-test) -> all become "system", no code change
| File | Sites | Becomes |
|------|-------|---------|
| outreach.py | 17 (`engine.begin()/connect()`) | untouched; `engine` is the system engine (D-08) |
| outreach_routes.py | 2 | untouched |
| prospects.py | 2 | untouched |
| scrapes.py | 5 | untouched |
| pilot.py | 1 (`_save`) | untouched |
| bootstrap.py | default param `eng=engine`, `__main__` | untouched (owner) |
| conftest.py | cleanup + scratch_db create/drop | untouched (superuser; needs CREATEDB) |

Add one comment in `db.py` that `engine` is the system/owner engine so nobody uses it in tenant code. Optionally a grep test: no `engine.` import in agent.py, tools.py, faq.py, main.py.

### `system()` sites
main.py (lifespan tenant list, `/health`), pack.py:316 (`get_pack` reads `tenants`; this is on every chat turn, stays system), tenants.py `ensure_tenant`, admin.py `_rows(_tenant=None)`, evals/runner.py:332 (eval_runs insert). All stay; they now run on the superuser engine.

### `tx()` sites -> stay, but now run on `app_engine` under RLS
agent.py (about 10), tools.py (about 12), faq.py `seed_faq`, tenants.py `sync_faq`, admin.py (`_rows` tenant branch, `resolve_escalation`, `inbound`, `draft_followup`), main.py `/chat` (`tx()` with no tenant), evals/runner.py (110, 116, 131, 190, 325). Every statement already carries the tenant context.

### `settings.default_tenant_id` uses (non-test) and what each becomes
| Location | Becomes |
|----------|---------|
| db.py `tx()` (line 15), `record_event` (line 31) | **raise** if tenant is None (no fallback) |
| agent.py:31 `handle_turn`, :261 `_t()` | make `tenant_id` required; `_t()` deleted; thread tenant into `conversation_token`, `token_matches` |
| tools.py `_tid` and every `tenant_id=None` default | `tenant_id` required (keyword); `_tid` just `str()` |
| faq.py:14 `seed_faq` | required arg |
| pack.py:315 `get_pack(tenant_id=None)` | required arg (it is a read of `tenants`, but a missing tenant is still a bug) |
| main.py `/chat` | `tenant = Depends(chat_tenant)`; pass to `handle_turn`, `token_matches`, `conversation_token`, the closing `tx(tenant)` |
| admin.py `_redelivered`, `inbound` (x3), `draft_followup` (x3 incl. `get_pack`) | `scope.tenant_id` (admin without `X-Tenant-Id` -> legacy fallback, see S5) |
| triage.py:64 | RoofDesk own-funnel pack lookup (reads `tenants` only, D-08). Keep `settings.default_tenant_id` here, rename nothing |
| config.py | keep the setting (still used by triage, the admin legacy fallback, tests); edit the stale comment |
| migrations 001-003 | untouched (historical); 005 drops the column DEFAULTs |

Note this leaves `default_tenant_id` in three named places (triage, admin legacy fallback, tests). D-06 allows "remaining uses"; confirm with the user (Open Question 1).

## S2. DB role design

**Decision:** `engine` = system (owner, superuser in compose), `app_engine` = `app_rw`. D-10 option "second engine as owner" chosen over a `BYPASSRLS` role: no second role, no second password, and compose already runs the owner as superuser.

Why not a policy-based "system" path (a GUC like `app.system='on'` that a policy honours): the app role could set it itself, so any SQL injection defeats RLS. Rejected.

### db.py shape
```python
engine = create_engine(settings.database_url, pool_pre_ping=True)            # system/owner: bypasses RLS
app_engine = create_engine(settings.app_database_url or settings.database_url, pool_pre_ping=True)  # app_rw

def tx(tenant_id, eng=None):                      # tenant_id now required
    tid = str(uuid.UUID(str(tenant_id)))          # None raises before any SQL (str(None) is not a uuid)
    with (eng or app_engine).begin() as c: ...
```
`system(eng=None)` unchanged (defaults to `engine`). Existing tests pass `eng=` explicitly, unaffected.

**Silent-vacuous-RLS guard:** if `APP_DATABASE_URL` is unset the app falls back to the owner and RLS silently does nothing. Add `assert_rls_enforced()` (in db.py), called from the FastAPI lifespan and from the leak test: on `app_engine`, `SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user` must be false and `current_user` must not own `leads`. Raise at startup otherwise. TestClient without a `with` block does not run lifespan, so the pytest leak test calls it directly.

### Role creation, incl. the live DB (existing volume)
`db/init.sql` only runs on a fresh volume, and a SQL migration cannot read env. So:
1. `005_rls.sql` creates the role idempotently without a password:
   ```sql
   DO $$ BEGIN
     IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
       CREATE ROLE app_rw NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
     END IF;
   END $$;
   ```
   Roles are cluster-wide, so scratch DBs created by tests share it; the `IF NOT EXISTS` handles that.
2. `bootstrap_schema` (after `apply_migrations`, every start): if `settings.app_db_password` is set, run `ALTER ROLE app_rw LOGIN PASSWORD <literal>`. Build the literal server-side: `c.execute(text("SELECT format('ALTER ROLE app_rw LOGIN PASSWORD %L', :p)"), {"p": pw}).scalar()` then `c.exec_driver_sql(stmt)`. Never f-string the password. This works identically on a fresh volume and on the live DB, and rotates the password on restart. Note the statement may appear in server logs if `log_statement` is on.
3. The migrator needs CREATEROLE. In compose it is superuser. On a hosted DB where the owner is not superuser, document that `app_rw` must be pre-created by an admin.

### Compose changes (docker-compose.yml, api service; global override inherits)
```yaml
APP_DATABASE_URL: postgresql+psycopg://app_rw:${APP_DB_PASSWORD:-app_rw_dev}@db:5432/leadpilot
APP_DB_PASSWORD: ${APP_DB_PASSWORD:-app_rw_dev}
# PUBLIC_DEMO_TENANT_ID intentionally NOT set on the branch (D-05)
```
`DATABASE_URL` stays the leadpilot superuser (migrations/bootstrap/system/conftest). New settings: `app_database_url: str = ""`, `app_db_password: str = ""`, `public_demo_tenant_id: str = ""`. `SECRET_HINTS` masking already covers names containing "password"/"key". `docker-compose.global.yml` needs no change (ports only). The `roofdesk-global` project/volume applies 005 on next API start with no volume recreation.

### Which connects how
| Actor | Connection |
|-------|-----------|
| API tenant paths (`tx`) | `app_rw` via `APP_DATABASE_URL` |
| `bootstrap_schema` / migrations / lifespan | `engine` (owner) |
| conftest cleanup, scratch_db, raw test setup via `engine` | owner/superuser (bypass) |
| evals/runner.py | `tx(t)` -> app_rw; `system()` -> owner. No code change; runs via `docker compose exec api`, which has both URLs |
| test_rls_proof scratch DB | needs rewrite (S6) |

### Grants (in 005, explicit)
```sql
GRANT USAGE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON leads, conversations, messages, slots, appointments, faq_chunks,
      tool_calls, escalations, events, llm_calls TO app_rw;
GRANT SELECT, INSERT ON agent_events TO app_rw;          -- append-only: no UPDATE/DELETE/TRUNCATE
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;
-- pgvector: the <=> operator and vector type need no extra grant (extension objects are PUBLIC-usable)
```
No grant on tenants, tenant_api_keys, outreach tables, eval tables. FK checks (including composite FKs) run with RLS bypassed as RI triggers, so `app_rw` needs no `tenants` privilege. [ASSUMED: Postgres RI-bypasses-RLS behaviour from training; the leak test inserting through app_rw proves it]

## S3. Policies (policy SQL)

Tables (11): leads, conversations, messages, slots, appointments, faq_chunks, tool_calls, escalations, events, llm_calls, agent_events.

```sql
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leads','conversations','messages','slots','appointments','faq_chunks',
                           'tool_calls','escalations','events','llm_calls','agent_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)$p$, t);
  END LOOP;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leads','conversations','messages','slots','appointments','faq_chunks',
                           'tool_calls','escalations','events'] LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id DROP DEFAULT', t);
  END LOOP;
END $$;
```
Notes:
- `NULLIF(..., '')` is required: after a transaction-local `set_config` ends, a pooled connection reports `''` (not NULL) for the placeholder GUC, and `''::uuid` raises instead of returning 0 rows. [VERIFIED: pattern proven in test_rls_proof.py `test_setting_is_transaction_local`]
- **faq_chunks (pgvector):** same policy; `lookup_faq` already filters `tenant_id = :t` and there is no ANN index (init.sql has none), so no filtered-index recall problem at tens of rows per tenant.
- **agent_events:** same policy plus `GRANT SELECT, INSERT` only. The 004 `BEFORE UPDATE OR DELETE` row trigger and `BEFORE TRUNCATE` trigger stay. App role cannot `DISABLE TRIGGER` (not owner), which closes the 004 comment "a superuser can still disable triggers". `test_tenancy.test_agent_events_append_only` runs on the scratch DB as superuser, so it still sees "append-only" messages; if anyone moves it to `app_rw` the error becomes `permission denied`, so match either.
- **llm_calls:** nullable `tenant_id`. Under the policy NULL rows (outreach) are invisible to and un-insertable by `app_rw`. Correct: outreach code uses `engine` (system), and tenant code always writes a tenant id (`agent._log_llm`). Do not add `OR tenant_id IS NULL`.
- `tenant_api_keys`, `tenants`: no RLS, no `app_rw` grant (defence by privilege, not policy).
- `FORCE` also applies to the table owner, so a non-superuser owner as system engine would see nothing. Superuser or `BYPASSRLS` owner required (S2).
- `ON CONFLICT DO NOTHING` / `UPDATE ... RETURNING` need the SELECT side of the policy; `FOR ALL` (default) covers it.

## S4. `tenant_api_keys`: does NOT exist

`db/migrations/003_tenant_keys.sql` is composite UNIQUE/FK constraints (name is misleading); grep for `tenant_api_keys` in `db/` and `api/` finds nothing. [VERIFIED: grep] Create it in `006_tenant_api_keys.sql`:
```sql
CREATE TABLE IF NOT EXISTS tenant_api_keys (
  id serial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  key_hash text NOT NULL UNIQUE,            -- sha256 hex; the plaintext is never stored
  label text,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS tenant_api_keys_tenant_idx ON tenant_api_keys (tenant_id);
-- no GRANT to app_rw, no RLS: system context only (D-03)
```
`UNIQUE(key_hash)` is the lookup index. Lookup: `SELECT tenant_id FROM tenant_api_keys WHERE key_hash=:h AND revoked_at IS NULL`, then `hmac.compare_digest(row_hash, h)` as the D-01 belt. Reject early (401, no DB hit) if the key lacks the `rd_live_` prefix or exceeds ~128 chars. Add `tenant_api_keys` cleanup to conftest before `DELETE FROM tenants WHERE slug LIKE 'test-%'` (FK would otherwise block the delete and recreate the leftover-rows problem).

## S5. Endpoint inventory and auth

Dependency design (one module `auth.py`):
- `require_admin`: unchanged behaviour (403 on bad/missing admin key; tests assert 403). Re-exported from `admin.py` so `outreach_routes.py` and `triage.py` imports keep working.
- `require_tenant(x_api_key=Header(""))` -> tenant id str; 401 `{"detail":"unauthorized"}` for missing/unknown/revoked (same body for all).
- `require_scope`: returns `Scope(tenant_id: str | None, is_admin: bool)`. Order: valid `X-API-Key` -> tenant scope (any `X-Tenant-Id` header ignored); else valid `X-Admin-Key` -> `Scope(tenant_id=X-Tenant-Id or None, admin=True)`; else 401/403. Present-but-invalid `X-API-Key` is 401, never falls through to the demo or admin path.
- `chat_tenant`: key present -> resolve (invalid is 401); absent -> `settings.public_demo_tenant_id` if set and a valid uuid; else 401.

| Route | Today | Phase 6 |
|-------|-------|---------|
| `GET /leads`, `/leads/{id}`, `/conversations`, `/conversations/{id}` | admin router | `require_scope`; `_rows(..., _tenant=scope.tenant_id)` (admin w/o header = cross-tenant, tenant key = RLS-scoped) |
| `GET /metrics` | admin | `require_scope`; tenant scope returns conversation/funnel/llm/daily only, `eval_runs=[]`, no `outreach` (app_rw has no grant on eval_*/outreach tables; querying them would raise `permission denied`). Admin = unchanged cross-tenant output |
| `GET /admin/escalations`, `POST /admin/escalations/{id}/resolve` | admin | `require_scope`; resolve uses `tx(tenant)` (needs a tenant: header or legacy fallback) |
| `POST /webhooks/inbound` | admin, default tenant | `require_scope` + tenant required; pass `tenant_id` to `handle_turn`, `_redelivered`, event insert, info select |
| `GET /admin/followups/due`, `POST /admin/followups/{cid}/draft` | admin | `require_scope`; due is cross-tenant under admin without header (add `tenant_id` to the select so n8n can later pass `X-Tenant-Id`); draft requires tenant |
| `POST /chat` | public | `chat_tenant`; body keeps `message`, `conversation_id`, `conversation_token` only (pydantic ignores extras; optionally `extra="forbid"`: a stray `tenant_id` then 422s, which also satisfies "ignored" but breaks lenient clients; prefer ignore + test) |
| `/triage` | admin | unchanged (`require_admin`, own funnel pack) |
| `/admin/campaigns*`, prospects, outreach/*, scrapes, call-list, `/webhooks/outreach-event` | admin | unchanged (D-08) |
| `/intake`, `/pilot-requests`, `/speak`, `/transcribe` | public + rate limit | unchanged (own funnel / stateless) |
| `/health`, `/showcase`, static mount | public | unchanged (health uses system engine; optionally also ping `app_engine` so a bad app role fails health) |
| NEW `GET/POST /admin/tenants` | -- | `require_admin`; list id, slug, name, timezone, pack_slug; create via `ensure_tenant(pack_slug)` |
| NEW `POST /admin/tenants/{tid}/keys` | -- | `require_admin`; returns plaintext once `{id, key, label}` |
| NEW `GET /admin/tenants/{tid}/keys` | -- | `require_admin`; id, label, created_at, revoked_at (never the hash) |
| NEW `POST /admin/tenants/{tid}/keys/{kid}/rotate`, `.../revoke` | -- | `require_admin`; rotate = INSERT new + `UPDATE old SET revoked_at=now() WHERE id=:k AND tenant_id=:t AND revoked_at IS NULL` in one `system()` tx; 404 if old not active |

**How existing n8n/dashboard callers keep working:** they send only `X-Admin-Key`. Read routes become cross-tenant under admin (exactly what the dashboard does today, since `_rows` without tenant already uses `system()`). The four tenant-write routes (inbound, followup draft, resolve) need a tenant even for admin callers: accept optional `X-Tenant-Id` (admin only) and, when absent, fall back to `settings.default_tenant_id` with a `log.warning`, documented as removed in Phase 8 when n8n sends tenant keys. This is the one place the config constant survives in a data path; alternative is to 400 and break the live n8n flows, which CONTEXT forbids ("keep admin-key access to the existing n8n-called endpoints working"). Flag to user.

**CORS:** `allow_headers=["content-type"]` blocks a browser from sending `X-API-Key`. Correct for the keyless demo; do not add it (a key in browser JS is public by definition). Note for a future tenant widget.

**`/chat` details:** `token_matches`/`conversation_token` currently default the tenant; they must take the resolved tenant so a conversation id from tenant A with tenant B's key is 404 (RLS also guarantees it).

**Startup seeding:** lifespan lists tenants via `system()`, then `seed_faq(tenant)` via `tx` on `app_engine`: works under RLS. Add `assert_rls_enforced()` before it.

## S6. pytest and evals under RLS

### What changes for pytest
`engine` stays superuser, so raw `with engine.begin()` setup/readback in tests bypasses RLS (fine, and unscoped DELETE/UPDATE there still work). Code under test (`tx`) now runs as `app_rw`. Things that **break and need edits**:
1. **Raw inserts without `tenant_id` (default dropped):** `test_admin.py` lines 49-50 (`leads`, `conversations`), 65 (`messages`), 75 (`escalations`); `test_chat_security.py` 31-32. Add `tenant_id` (use `settings.default_tenant_id`).
2. **Calls relying on the default tenant:** about 26 in `test_agent.py`, 19 in `test_tenancy.py`, 11 in `test_isolation.py`, plus `test_admin` (2), `test_chat_security` (2), `test_logging_tenant` (2), `test_service_type` (3), `test_eval_gate`/`test_pack` (1 each): `agent.handle_turn(...)`, `tools.*(...)`, `get_pack()`, `tx()` with no tenant. Fastest: a conftest constant `T = settings.default_tenant_id` and add `tenant_id=T`. Do not keep a default in production code to avoid this.
3. **`test_rls_proof.py`:** its fixture runs `CREATE POLICY tenant_isolation` on leads/slots in a scratch DB that `bootstrap_schema` has already given the real policy, so it errors with "policy already exists". Rewrite: bootstrap scratch DB, set the `app_rw` password (or create the login via the same bootstrap step), build `role_eng` from `make_url(settings.database_url).set(username="app_rw", password=..., database=db_name)`, drop the probe role and policy creation, keep the assertions (own rows only, no-context 0 rows, cross-tenant insert rejected, tx-local, superuser sees all) and parametrize over all 11 tables.
4. **`test_tenancy.py`:** the schema test asserting `tenant_id` DEFAULT contains Summit (about lines 118-122, `rows[t][1] contains A`) must now assert no default. `TENANT_TABLES` constant lacks `llm_calls`/`agent_events`: fine, add to the new catalog test instead.
5. **`test_migrations.py`:** `_seed_baseline` inserts legacy rows before migrations run, so unaffected (005 runs last). Scratch DB queries run as superuser, unaffected. Add: 005 and 006 applied; second run no-op; role exists.
6. **conftest cleanup:** keep on `engine`. Add `tenant_api_keys` delete for `test-%` tenants. Harden agent_events: delete rows for test-% tenants regardless of id (trigger already disabled in that transaction).

### Risk: unscoped DELETE/UPDATE under RLS
On `app_rw` with no tenant context, `DELETE`/`UPDATE` silently affect 0 rows (no error). Only matters where code or tests use `tx`/`app_engine`: evals/runner.py `reset_db`, `steal_first_slot` all carry `tenant_id=:t` and run inside `tx(t)`, so they work and are properly scoped. `test_agent.clean` (`DELETE FROM appointments; UPDATE slots SET is_booked=false`, unscoped) runs on `engine` (superuser), still wipes all tenants (harmless). Rule for the planner: never switch those raw test helpers to `app_engine`.

### Evals (D-13)
No runner edits needed: `ensure_tenant` (system), `ensure_slots`/`sync_faq`/`handle_turn`/readbacks (`tx(t)` -> `app_rw`), `eval_runs` insert (system). Roofing behaviour cannot change except where a path forgets tenant context (it would now return 0 rows or raise), which the gate exposes. Run order for verification: apply migrations -> `pytest` -> `make eval-gate` (roofing 94/96 same two failures `voice-over-explainer`, `voice-indecisive`) -> `--pack bright-smile-dental --gate` (43/43). [CITED: 05-06-PLAN.md for expected ids]

### Cause of the intermittent post-eval pytest failure
Most likely failing test: `api/app/test_agent.py::test_slots_are_topped_up_when_the_calendar_runs_short`. Its `dupes` query is
`SELECT count(*) FROM (SELECT start_time FROM slots GROUP BY 1 HAVING count(*) > 1)` with no tenant filter, while migration 003 intentionally allows the same `start_time` across tenants (`slots_tenant_start_key`). After an eval, a non-`test-` tenant (`bright-smile-dental`, Europe/Zurich hours 8-17, per `businesses/bright-smile-dental/calendar.yaml`) holds 14 days of slots; many Zurich hours map to UTC instants equal to roofing's 9/11/14/16 UTC (e.g. 11:00 UTC = 12/13:00 Zurich depending on DST), so cross-tenant duplicates exist and the assertion fails. `conftest.remove_test_data` deletes `slots WHERE tenant_id <> default` at session end, so the immediately following run passes: that is the "intermittent" signature. Leftover `test-%` tenants using the roofing calendar (test_isolation `both` fixture seeds `ensure_slots` per test tenant) produce the same duplicates if a prior session aborted before cleanup. [ASSUMED: static analysis; tests not run per instructions]

Fix: `GROUP BY tenant_id, start_time` (or `WHERE tenant_id=:d` and `max(start_time)` for the default tenant). Also harden conftest: the blanket `DELETE ... WHERE tenant_id <> default` is destructive on any DB holding a real second tenant (dental eval data gets wiped by pytest); scope all those deletes to tenants whose slug is `LIKE 'test-%'`. That would then leave the dental eval tenant's slots in place across pytest runs, which is another reason the dupes query must be tenant-scoped (do both).

Cause of leftover `test-%` tenant rows blocking cleanup (Phase 5 summary, 05-01-SUMMARY.md): the delete list covers every child table by `tenant_id <> default` except `agent_events`, which is deleted only for `id > first_event` (append-only, so it must be by id range). A test tenant that has `agent_events` with `id <= first_event` (left by a session that died before teardown, or any concurrent writer) is never deleted, so `DELETE FROM tenants WHERE slug LIKE 'test-%'` fails the FK and the failure then recurs every session until cleaned by hand. [ASSUMED] Hardening in item 6 above fixes it. To capture ground truth next time: run `pytest -q -x -p no:cacheprovider` immediately after an eval and record the first failing node id.

## S7. Leak test design (`api/app/test_leak.py`, SEC-04, D-12)

Fixture: two tenants with `test-leak-a-<hex>`/`test-leak-b-<hex>` slugs on the `summit-roofing` pack (fresh uuids, like `test_isolation.both`), `faq.seed_faq(t, reload=True)` and `tools.ensure_slots(t)` with `llm.embed` monkeypatched to `test_isolation._hash_vec` and `llm.chat` faked, `monkeypatch.setattr(settings, "admin_api_key", "adm")`, keys issued via the new `auth` functions (system engine), `TestClient(app)` (no lifespan). Seed distinguishable data per tenant (lead name, FAQ text with a unique token, a closed conversation, an escalation).

Cases (parametrize A/B where sensible):
- No `X-API-Key` on `/chat` with `public_demo_tenant_id=""` -> 401; wrong key -> 401; revoked key -> 401; rotated old key -> 401, new key -> 200; same generic body for all.
- `PUBLIC_DEMO_TENANT_ID` set: keyless `/chat` works and lands in that tenant; keyless `/leads` still 401/403; an *invalid* `X-API-Key` with the demo set is still 401 (no fallthrough).
- Body `tenant_id` = B with key A creates the row under A (assert via system engine); `X-Tenant-Id: B` header with key A is ignored.
- Chat with key A returns a conversation; continuing it with key B and A's token -> 404.
- Own-rows-only under tenant keys: `/leads`, `/leads/{id}` (other tenant's id -> 404), `/conversations`, `/conversations/{id}`, `/admin/escalations`, `/metrics` (counts equal that tenant's seeded numbers; no `outreach`/`eval_runs` keys), `/admin/followups/due`.
- FAQ: `tools.lookup_faq("<unique token of B>", tenant_id=A)` returns none of B's chunks; slots: `get_available_slots(tenant_id=A)` ids are all A's; `book_appointment(lead_A, slot_B, tenant_id=A)` raises "slot unavailable".
- Tenant key on admin-only routes (`/admin/tenants`, key endpoints, `/admin/campaigns`, `/triage`) -> 403; admin key without header on `/leads` -> rows from both tenants (cross-tenant is only available to super-admin, SEC-05).
- DB level on `app_engine` with no `tx`: for each of the 11 tables `count(*) == 0` despite seeded rows; `INSERT` without context raises "row-level security"; `app_rw` has no privilege on `tenants`, `tenant_api_keys`, `prospects` (`has_table_privilege`).
- Catalog tests: every table with a `tenant_id` column has `relrowsecurity AND relforcerowsecurity` and no `column_default`; `assert_rls_enforced()` passes; `app_rw` is `NOSUPERUSER NOBYPASSRLS` and not the owner of `leads`.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Row isolation | Per-query `WHERE tenant_id` as the only guard | RLS FORCE + `tx()` | One forgotten filter leaks data |
| Key storage | Reversible encryption, bcrypt/passlib | sha256 + `secrets` | 256-bit random secret; slow hashes are for passwords |
| Constant-time compare | `==` | `hmac.compare_digest` | already in repo |
| Migrations | Alembic | numbered SQL via `bootstrap.py` | project decision |
| Password into `ALTER ROLE` | f-string | server-side `format('%L')` | quoting/injection |

## Common Pitfalls

### 1. RLS silently off because the app connects as owner/superuser
**What goes wrong:** the whole suite passes but nothing is enforced. **Avoid:** `assert_rls_enforced()` at startup and in a test; compose sets `APP_DATABASE_URL`. **Sign:** `app_database_url` empty.

### 2. `ALTER DEFAULT PRIVILEGES` grants the keys table to `app_rw`
Use explicit grants; the catalog test asserts `has_table_privilege('app_rw','tenant_api_keys','SELECT')` is false.

### 3. Non-superuser owner is locked out by FORCE
System engine returns 0 rows on a hosted DB with a plain owner. **Avoid:** superuser or `ALTER ROLE owner BYPASSRLS`; startup check selects `count(*) FROM tenants` via system (tenants has no RLS) and a policy-table probe.

### 4. Empty-string GUC cast
Without `NULLIF`, `''::uuid` raises on a reused pooled connection. Keep the NULLIF form exactly.

### 5. Default dropped -> raw INSERTs fail NOT NULL
Hits `test_admin`, `test_chat_security`, and any later migration that backfills via DEFAULT. Run 005 last among data-bearing steps.

### 6. `llm_calls` outreach rows
Outreach inserts must stay on the system engine. A stray `tx()` there would fail the policy `WITH CHECK` (NULL tenant). Keep outreach on `engine`.

### 7. Tenant-key fall-through
An invalid `X-API-Key` must not fall through to the demo tenant or the admin path. Covered in tests.

### 8. `tx(None)` must raise
Otherwise tests and code keep silently using Summit and the leak test proves nothing. Add a unit test.

### 9. `/metrics` under a tenant key touching eval/outreach tables
`app_rw` has no privilege there: `permission denied` 500. Branch on scope.

### 10. `get_pack` on every turn uses the system engine
Fine, but it means every chat request opens a second pooled connection class. Keep pool sizes modest; no change needed at current scale.

### 11. CORS
Do not add `x-api-key` to `allow_headers` for the public demo.

## Code Examples

### Key issue / lookup (auth.py sketch)
```python
KEY_PREFIX, MAX_KEY_LEN = "rd_live_", 128

def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def issue_key(tenant_id: str, label: str | None = None) -> dict:
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with system() as c:
        kid = c.execute(text("INSERT INTO tenant_api_keys (tenant_id, key_hash, label) VALUES (:t,:h,:l) RETURNING id"),
                        {"t": tenant_id, "h": _hash(key), "l": label}).scalar_one()
    return {"id": kid, "key": key, "label": label}      # plaintext leaves only here

def require_tenant(x_api_key: str = Header("")) -> str:
    if not x_api_key.startswith(KEY_PREFIX) or len(x_api_key) > MAX_KEY_LEN:
        raise HTTPException(401, "unauthorized")
    h = _hash(x_api_key)
    with system() as c:
        row = c.execute(text("SELECT tenant_id::text, key_hash FROM tenant_api_keys "
                             "WHERE key_hash=:h AND revoked_at IS NULL"), {"h": h}).first()
    if not row or not hmac.compare_digest(row.key_hash, h):
        raise HTTPException(401, "unauthorized")
    return row.tenant_id
```

### Rotate (one transaction)
```python
with system() as c:
    n = c.execute(text("UPDATE tenant_api_keys SET revoked_at=now() WHERE id=:k AND tenant_id=:t AND revoked_at IS NULL"),
                  {"k": kid, "t": tid}).rowcount
    if not n: raise HTTPException(404, "key not found")
    # then the INSERT of the new key in the same `with`
```

### Bootstrap password step
```python
def set_app_role_login(eng=engine) -> None:
    if not settings.app_db_password:
        return
    with eng.begin() as c:
        stmt = c.execute(text("SELECT format('ALTER ROLE app_rw LOGIN PASSWORD %L', :p)"), {"p": settings.app_db_password}).scalar()
        c.exec_driver_sql(stmt)
```
Call at the end of `bootstrap_schema` after `apply_migrations(eng)`.

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| App connects as compose superuser | `app_rw` non-owner under FORCE RLS | RLS actually enforced (core change) |
| Default tenant fallback everywhere | explicit tenant from credential | silent Summit fallback removed |

## Runtime State Inventory (migration phase)

| Category | Items Found | Action |
|----------|-------------|--------|
| Stored data | Live demo DB rows all carry Summit `tenant_id` (002 backfill); no data change needed | none; 005 is schema-only |
| Live service config | n8n workflows send only `X-Admin-Key` and rely on default tenant for inbound/followups | keep working via admin legacy fallback; Phase 8 migrates |
| OS-registered state | None found | none |
| Secrets/env vars | New `APP_DB_PASSWORD`, `APP_DATABASE_URL`; optional `PUBLIC_DEMO_TENANT_ID` (deploy only, user action before roofdeskai.com `/chat` keeps working keyless) | add to compose and deploy env; never commit values |
| Build artifacts | None | none |

Live demo risk: if roofdeskai.com is deployed from this branch without `PUBLIC_DEMO_TENANT_ID` set, `/chat` returns 401. Set it to `00000000-0000-0000-0000-000000000001` at deploy. Not set on the branch by decision.

## Environment Availability

Not probed (read-only instruction; no commands that touch Docker/Postgres were run). Execution depends on the `roofdesk-global` compose stack (Postgres 16 pgvector image, superuser `leadpilot`) and host Ollama (embeddings for evals). Planner should include a first task that confirms `make g-up` is healthy and the DB user is superuser (`SELECT rolsuper FROM pg_roles WHERE rolname=current_user`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 (in `api/requirements.txt`) |
| Config | none (conftest in `api/app/conftest.py`) |
| Quick run | `make g-test ARGS="app/test_leak.py app/test_rls_proof.py app/test_migrations.py -x"` |
| Full suite | `make g-test` |
| Eval gate | `make eval-gate` and `make g-eval ARGS="--pack bright-smile-dental --gate"` |

### Requirements -> Test Map
| Req | Behavior | Type | Command | Exists |
|-----|----------|------|---------|--------|
| SEC-01 | issue shows key once, hash only stored, rotate, revoke -> 401 | integration | `pytest app/test_keys.py -x` | Wave 0 |
| SEC-02 | no key 401, body/header tenant ignored, demo fallback rules | integration | `pytest app/test_leak.py -k "key or body or demo"` | Wave 0 |
| SEC-03 | FORCE RLS, non-owner, defaults dropped, no-context 0 rows | integration (scratch DB + catalog) | `pytest app/test_rls_proof.py app/test_migrations.py` | rewrite |
| SEC-04 | cross-tenant leak test | integration | `pytest app/test_leak.py` | Wave 0 |
| SEC-05 | tenant key cannot hit admin/cross-tenant | integration | `pytest app/test_leak.py -k admin` | Wave 0 |

### Sampling
Per task: affected test file; per wave: full pytest; phase gate: full pytest green, roofing gate 94/96, dental 43/43.

### Wave 0 Gaps
- [ ] `api/app/test_keys.py`, `api/app/test_leak.py`
- [ ] Rewrite `api/app/test_rls_proof.py` against real policies
- [ ] Fix `test_admin.py`, `test_chat_security.py` raw inserts; update `test_tenancy.py` default assertion; thread tenant through test callers
- [ ] conftest: `tenant_api_keys` cleanup, test-slug-scoped deletes, agent_events by tenant
- [ ] Fix `test_agent.py` dupes query to be per tenant

## Security Domain

| ASVS | Applies | Control |
|------|---------|---------|
| V2 Authentication | yes | per-tenant API keys, sha256, compare_digest, generic 401 |
| V3 Session Management | no | stateless keys; conversation token already per conversation |
| V4 Access Control | yes | RLS FORCE + non-owner role + scope dependency; admin/tenant scope split |
| V5 Input Validation | yes | key prefix/length check; uuid validation in `tx`; pydantic schemas |
| V6 Cryptography | yes | `secrets` + sha256, no custom crypto |

| Threat | STRIDE | Mitigation |
|--------|--------|-----------|
| Cross-tenant read via forgotten filter | Information disclosure | RLS backstop + leak test |
| Tenant spoofing via body/header | Spoofing | tenant only from credential; header honoured only with admin key |
| Key theft from DB | Info disclosure | hash only; plaintext shown once |
| Key brute force | Spoofing | 256-bit entropy; add `X-API-Key` failures to the existing IP limiter if cheap (optional) |
| Role password in logs | Info disclosure | settings masking already covers `password`; `ALTER ROLE` statement may be in server log if `log_statement` enabled |
| SQL injection altering GUC | Elevation | app role cannot bypass RLS; no policy-based system path |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Post-eval failure is the cross-tenant slot-duplicate query in test_agent.py | S6 | Wrong test fixed; confirm with failing node id |
| A2 | Leftover test-% blocking is agent_events with id <= first_event | S6 | Cleanup hardening still harmless |
| A3 | RI (FK) checks bypass RLS so app_rw needs no `tenants` grant | S2 | Add `GRANT SELECT ON tenants` (no RLS) if inserts fail |
| A4 | NOLOGIN role + later `ALTER ROLE ... LOGIN PASSWORD` from bootstrap works for the migrator (superuser) | S2 | Pre-create role in init script |
| A5 | Dental slot instants overlap roofing UTC hours | S6 | Cause then is test-% leftovers only; fix identical |

## Open Questions (RESOLVED)

1. **Admin legacy tenant fallback:** n8n sends only the admin key to inbound/followups/escalation-resolve. Recommendation: optional `X-Tenant-Id` (admin only), else `settings.default_tenant_id` with a warning, removed in Phase 8. Needs user confirmation since it is a remaining `default_tenant_id` use in a data path (D-06).
   **RESOLVED (planner decision):** optional `X-Tenant-Id` header on admin-key calls, fallback to `default_tenant_id` with a logged warning until Phase 8. Documented deviation from D-06; the user must be told in the final report.
2. **`default_tenant_id` kept for triage's own-funnel pack:** recommend keep; confirm.
   **RESOLVED:** keep `default_tenant_id` for triage own-funnel pack lookup only (recorded in 06-04).
3. **Hosted deploy owner role:** is the production migrator a superuser? If not, one-time `ALTER ROLE ... BYPASSRLS` by an admin.
   **RESOLVED:** local dev owner is superuser; for hosted deploy this is a documented step in the 06-06 SUMMARY deploy notes.
4. **Key endpoint paths** chosen as `/admin/tenants/{tid}/keys...` (discretion).
   **RESOLVED:** adopted as written.

**VALIDATION.md waived:** no 06-VALIDATION.md is produced for this project (same as phases 2-5); validation is via the per-plan automated verify commands and plan 06-06 gates.

## Sources

### Primary (HIGH, direct reads)
- `.planning/phases/06-.../06-CONTEXT.md`, ROADMAP.md Phase 6, REQUIREMENTS.md SEC-01..05
- `db/init.sql`, `db/outreach.sql`, `db/migrations/001-004*.sql`
- `api/app/{db,admin,main,config,bootstrap,tenants,tools,faq,agent,pack,pilot,triage,intake,outreach_routes,ratelimit,logctx}.py`
- `api/app/conftest.py`, `test_rls_proof.py`, `test_isolation.py`, `test_tenancy.py`, `test_admin.py`, `test_agent.py`, `test_migrations.py`, `test_chat_security.py`, `test_tenants.py`
- `docker-compose.yml`, `docker-compose.global.yml`, `Makefile`, `evals/runner.py`, `dashboard/lib/data.ts`, `n8n/workflows/*.json` (endpoint grep)
- `businesses/*/calendar.yaml`, `05-01-SUMMARY.md`

### Secondary (MEDIUM)
- Postgres RLS semantics (FORCE applies to owner; superuser bypass; RI bypass; custom GUC empty-string after tx-local reset) from training knowledge, partly corroborated by `test_rls_proof.py` behaviour. Not re-fetched this session.

## Metadata

**Confidence:** inventory HIGH; role/policy design MEDIUM-HIGH; pytest-failure cause MEDIUM (unrun)
**Research date:** 2026-11-04
**Valid until:** 2026-12-04 (stable domain; invalidated by new tables/modules in Phase 7)
