# Phase 2: Tenants, Migrations and DB Plumbing - Research

**Researched:** 2026-11-03
**Domain:** Postgres 16 (pgvector image) schema migration, SQLAlchemy 2 / psycopg3 raw-SQL plumbing, tenant context, RLS proof
**Confidence:** HIGH for repo facts (read from code and the live branch-stack DB); MEDIUM for Postgres/RLS semantics (training knowledge, not re-fetched; every behaviour is checkable by the scratch-DB proof in section 6)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Numbered files `db/migrations/NNN_name.sql`, applied in order by a small runner in `bootstrap.py`, each in its own transaction, recorded in `schema_migrations(version, applied_at)`. No Alembic.
- **D-02:** `init.sql` stays the baseline for an empty DB (schema as of `v1-roofing`); migrations run after it on every start, so fresh and live DBs converge. Migration 001 creates `tenants`; later ones add columns.
- **D-03:** Expand/contract: `tenant_id` is added nullable, backfilled to the default tenant, then set NOT NULL with a column DEFAULT of the default tenant id (so unmodified code keeps working). The DEFAULT is dropped in Phase 6, not here.
- **D-04:** Proven on a copy of a populated DB (dump from the branch stack, restore to a scratch DB, migrate, run unit tests plus the gate), never on the live volume.
- **D-05:** `tenants(id uuid pk, slug unique, name, timezone, pack_slug, created_at)`. Default tenant: slug `summit-roofing`, fixed uuid constant in config, timezone `America/Denver`.
- **D-06:** `tenant_id` on leads, conversations, slots, appointments, faq_chunks and the per-conversation tables (messages, tool_calls, llm_calls, escalations, events). Child tables carry it too, with composite FKs `(tenant_id, id)` where cheap.
- **D-07:** Uniques become composite: `slots(tenant_id, start_time)`, `conversations(tenant_id, external_id)`, `appointments(tenant_id, slot_id)` and `(tenant_id, lead_id)`.
- **D-08:** Outbound tables (`outreach.sql`: prospects, campaigns, drafts, replies, pilot) get no `tenant_id` (TEN-06). A test asserts this.
- **D-09:** `db.tx(tenant_id)` = context manager over `engine.begin()` running `SELECT set_config('app.tenant_id', :t, true)` first. `db.system()` = explicit untenanted context (bootstrap, outreach, pilot, admin cross-tenant). Every `engine.begin()` call site in tenant code moves to `tx()`; call-site inventory is plan 1 research.
- **D-10:** `tenant_id` passed explicitly down the call chain (`handle_turn`, tools, faq) with the default tenant as parameter default; no contextvar magic.
- **D-11:** App role today is the compose Postgres superuser, so RLS does nothing. Phase 2 only records this and adds the non-owner `app` role plus FORCE RLS on a test database to prove the pattern; production switch is Phase 6.
- **D-12:** `ensure_slots(tenant_id)` checks NOT EXISTS per tenant. Slot hours stay roofing constants until Phase 3.
- **D-13:** `seed_faq(tenant_id)` early-returns only if that tenant already has rows; reload is delete-then-insert per tenant. `lookup_faq` filters by tenant_id in SQL.
- **D-14:** A `logging.Filter` adds `tenant_id` to records from a contextvar set inside `db.tx()` callers/request middleware; log format gains `tenant=%(tenant_id)s`.
- **D-15:** `agent_events(id, tenant_id, conversation_id, kind, payload jsonb, created_at)` append-only (trigger blocks UPDATE/DELETE). Written for turn start, tool call, escalation. Existing `events` table stays.
- **D-16:** Every plan ends with pytest in the branch stack api container and a `make eval-gate` run (subset mid-phase, full before verification). Roofing stays 94/96 with the same two failures.

### Claude's Discretion
Migration file naming details, exact set of child tables getting composite FKs, test layout.

### Deferred Ideas (OUT OF SCOPE)
- Per-tenant API keys, RLS enforcement in the running app, dropping the default tenant (Phase 6)
- Moving slot hours/timezone into the pack (Phase 3)
- Tenant-scoped admin metrics endpoints (Phase 6, SEC-05)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEN-01 | Apply numbered SQL migrations to a live DB without recreating the volume | Section 3 runner design; section 5 dump/restore proof |
| TEN-02 | `tenant_id` on tenant tables, composite uniques | Section 2 table-by-table DDL plan |
| TEN-03 | All tenant access through `db.tx(tenant_id)` | Section 1 call-site inventory; `tx()`/`system()` sketch |
| TEN-04 | Slots and FAQ seeding per tenant | Sections 2, 7 (faq sequence bug, slot NOT EXISTS) |
| TEN-05 | Tenant-stamped logs and append-only `agent_events` | Logging notes; agent_events DDL |
| TEN-06 | Outreach/replies/pilot stay outside tenant model | Inventory marks them `system`; test asserts no column |
</phase_requirements>

## Summary

No new libraries are needed (SQLAlchemy 2 + psycopg3 + stdlib `logging`/`contextvars`/`uuid`) [CITED: .planning/research/STACK.md]. The work is: 4 SQL migrations, a ~25-line runner in `bootstrap.py`, a ~15-line `db.py`, mechanical conversion of ~45 `engine.begin()/connect()` call sites in tenant code, and a tenant parameter threaded through `handle_turn` -> tools -> faq.

Key facts verified against the running branch DB (`roofdesk-global-db-1`, PG 16.15, pgvector image, user `leadpilot` = superuser with BYPASSRLS) [VERIFIED: docker exec psql]: 18 tables; `slots` has **no unique on start_time at all** (only the PK), so D-07's new unique can fail on a populated DB with duplicates and must be pre-checked; `conversations.external_id`, `appointments.slot_id`, `appointments.lead_id` carry auto-named unique constraints that must be dropped by name; `faq_chunks_id_seq` is at 12 on the branch DB but `db/faq_seed.sql` inserts explicit ids without advancing the sequence, so a hosted-bootstrapped DB would collide on the next INSERT (matters once `seed_faq` is per tenant).

Because PG11+ makes `ADD COLUMN ... NOT NULL DEFAULT <constant>` a metadata-only operation that backfills implicitly, D-03's nullable-backfill-then-NOT-NULL dance collapses to one statement per table with the same end state. Use that.

**Primary recommendation:** Runner = `apply_migrations(eng)` called from `bootstrap_schema()` after the (guarded) baseline, always, under `pg_advisory_xact_lock`; `db.tx(tenant_id)` validates the uuid and calls `set_config(...,true)`; add `tenant_id` with `ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '<summit uuid>' REFERENCES tenants(id)`; prove on a `pg_dump` restored into a separate database in the branch cluster, with `DATABASE_URL` overridden only for that command.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema migrations | Database / Storage (SQL files) | API startup (runner) | Runs in `bootstrap_schema()` at API start; `db/` is mounted at `/srv/db` |
| Tenant context per transaction | API / Backend (`db.tx`) | Database (`set_config`, RLS in Phase 6) | Code passes tenant; DB enforces later |
| Slot generation, FAQ seeding | API / Backend | Database | Decisions in FastAPI, n8n not involved |
| Tenant-stamped logging | API / Backend | - | stdlib logging filter |
| Append-only events | Database (trigger) | API writes | Trigger is the enforcement |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | existing 2.x | `text()`, `engine.begin()` | Already used everywhere [VERIFIED: api/app/db.py] |
| psycopg (v3) | existing | `exec_driver_sql` multi-statement files | Existing bootstrap does this [VERIFIED: bootstrap.py] |
| stdlib `uuid`, `contextvars`, `logging`, `pathlib` | n/a | tenant id validation, log context, migration discovery | No dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Own ~25-line runner | Alembic | Locked out by D-01 and STACK.md |

**Installation:** none. **Package Legitimacy Audit:** no external packages installed this phase; slopcheck not needed.

## Architecture Patterns

### Data flow
```
API start (main.lifespan)
  -> bootstrap_schema(): lock -> [baseline if no public.leads] -> apply pending db/migrations/*.sql (each own tx, row in schema_migrations)
  -> for each tenant (system ctx): seed_faq(tenant_id)
request /chat | /webhooks/inbound | evals
  -> handle_turn(msg, cid, ..., tenant_id=DEFAULT) -> set log contextvar
       -> every DB touch: with db.tx(tenant_id) as c  (set_config app.tenant_id, tx-local)
       -> agent_events insert (turn start / tool call / escalation)
outreach*, prospects, scrapes, pilot, bootstrap, eval_runs -> db.system()
```

### Recommended structure
```
db/migrations/001_tenants.sql
db/migrations/002_tenant_columns.sql
db/migrations/003_tenant_keys.sql
db/migrations/004_agent_events.sql
api/app/db.py          # engine, tx(), system(), DEFAULT_TENANT_ID re-export
api/app/bootstrap.py   # bootstrap_schema(eng=engine), apply_migrations(eng)
api/app/test_migrations.py, test_tenancy.py, test_rls_proof.py
```

### Pattern: db.py
```python
# Sketch (not applied). DEFAULT_TENANT_ID lives in config (D-05) and equals the literal in migration 001/002.
@contextmanager
def tx(tenant_id=None):
    tid = str(uuid.UUID(str(tenant_id or settings.default_tenant_id)))  # validates; a bad value raises before SQL
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tid})
        yield c

@contextmanager
def system():
    with engine.begin() as c:   # explicit untenanted context
        yield c
```
Use `engine.begin()` for reads too (no `connect()` variant): `connect()` autobegins and `set_config(...,true)` only lives for a transaction; `begin()` makes that explicit and costs nothing. Keep `engine` exported (tests, evals import it).

### Anti-patterns
- Session-level `SET`/`set_config(...,false)`: pooled connection leaks the tenant (STACK.md).
- Passing tenant through a contextvar for SQL (D-10 forbids). The contextvar is for log stamping only.
- `INSERT ... ` that relies on the column DEFAULT for a non-default tenant: every tenant-table INSERT must pass `tenant_id` explicitly once a second tenant exists (the DEFAULT silently stamps Summit). Make the new/changed INSERTs explicit now; the DEFAULT only protects unmodified code (tests, scripts).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Concurrent-start safety | custom lock table | `pg_advisory_xact_lock(<const>)` at the start of each migration tx | Two api workers/containers starting together would both run 001 |
| Append-only | app convention | `BEFORE UPDATE OR DELETE` (+ `BEFORE TRUNCATE`) trigger raising | D-15 |
| Backfill | batched UPDATE loop | `ADD COLUMN ... NOT NULL DEFAULT const` | Metadata-only on PG16 |
| Migration framework | Alembic | the runner | D-01 |

## 1. Call-site inventory (engine.begin / engine.connect)

Line numbers from the working tree at research time. T = tenant context -> `db.tx(tenant_id)`; S = system -> `db.system()`. Tests are listed in section 4.

| File:line | Function / purpose | Ctx |
|---|---|---|
| api/app/db.py:5 | `engine = create_engine(settings.database_url, pool_pre_ping=True)` | home of tx()/system() |
| api/app/bootstrap.py:18 | `bootstrap_schema` guard + baseline | S |
| api/app/main.py:71 | `/health` `SELECT 1` | S |
| api/app/main.py:87 | `/chat` state + lead read | T |
| api/app/agent.py:223 | `_open` (conversation lookup by external_id, create lead + conversation) | T |
| api/app/agent.py:241 | `token_matches` | T |
| api/app/agent.py:247 | `_row` | T |
| api/app/agent.py:252 | `_exec` (used by `_save`, `_set_state`, `_set_lead_status`, `_log_llm`) | T |
| api/app/agent.py:261, 267 | `_last_message`, `_history` | T |
| api/app/tools.py:30 | `ensure_slots` | T |
| api/app/tools.py:43 | `get_available_slots` | T |
| api/app/tools.py:53 | `book_appointment` | T |
| api/app/tools.py:75 | `update_lead` | T |
| api/app/tools.py:85 | `lookup_faq` (vector query) | T |
| api/app/tools.py:95 | `_faq_keywords` | T |
| api/app/tools.py:103 | `escalate_to_human` | T |
| api/app/tools.py:116 | `_notify_escalation` channel read | T |
| api/app/tools.py:138 | `run` -> tool_calls insert | T |
| api/app/faq.py:29 | `seed_faq` | T (per tenant); the tenant list for startup comes from S |
| api/app/admin.py:25 | `_rows` generic reader: leads/conversations/escalations/metrics/followups/inbound info | S for cross-tenant admin reads today; but `_redelivered` and the inbound `info` query go through it and are per-tenant. Give `_rows` a `tenant_id` kwarg (default None -> system) so inbound passes the default tenant |
| api/app/admin.py:112 | `resolve_escalation` | T (default) |
| api/app/admin.py:147 | inbound `events` insert | T (default) |
| api/app/admin.py:174 | `draft_followup` | T (default) |
| api/app/pilot.py:45 | `_save` (campaigns/prospects) | S (TEN-06) |
| api/app/scrapes.py:26,33,41,50,82 | scrape_runs | S |
| api/app/outreach.py:169,178,188,203,214,226,236,250,282,295,358,364,391,414,433 | outreach, sequences, replies metrics | S |
| api/app/outreach_routes.py:79,98 | | S |
| api/app/prospects.py:179,217 | | S |
| evals/runner.py:66 | `reset_db`: `DELETE FROM appointments`, `UPDATE slots` (global!) | T default now; MUST become tenant-filtered before a second tenant has rows (Phase 5) |
| evals/runner.py:72 | `steal_first_slot` | T default |
| evals/runner.py:87, 144 | scenario readback / `assert_local_only` (by cid) | T default |
| evals/runner.py:263 | llm_calls aggregate by cid | T default |
| evals/runner.py:270 | `eval_runs`/`eval_results` writes | S |
| scripts/seed_demo.py:47 | back-dating conversations/messages/tool_calls | T default |

No other `create_engine` exists. `intake.py`, `policy.py`, `triage.py`, `replies.py`, `llm.py`, `mailer.py` have no direct engine use [VERIFIED: grep]. `replies.py` / `outreach_routes.py` replies handling is untenanted by TEN-06.

`handle_turn` signature (agent.py:32) gains `tenant_id` (default `settings.default_tenant_id`) and passes it to `_open/_save/...`, `tools.run(...)` and the tool functions (`fn(**args)` in `tools.run` means tenant must be bound with `functools.partial`/lambda at the call sites in `agent.py`, e.g. `_offer_slots` at agent.py:138, rather than put in model-supplied `args`). Tests monkeypatch `tools.lookup_faq` with signature `(query, k=3)` (test_agent.py:99,108,114): keep `tenant_id` a trailing keyword with default or those lambdas break.

## 2. Tables and DDL plan

Default tenant id: pick one constant, e.g. `00000000-0000-0000-0000-000000000001` [ASSUMED: any fixed uuid works; recognisable value makes Phase 6 default-removal greppable]. Put it in `config.py` as `default_tenant_id` and add a test that the migration literal equals it.

| Table | tenant_id | Notes |
|---|---|---|
| tenants (new, mig 001) | - | `id uuid PK DEFAULT gen_random_uuid()` (pgcrypto already loaded), `slug text UNIQUE NOT NULL`, `name`, `timezone text NOT NULL`, `pack_slug text`, `created_at`. Insert Summit with `ON CONFLICT (id) DO NOTHING`. |
| leads | NOT NULL DEFAULT, FK tenants | add `UNIQUE (tenant_id, id)` (target for composite FKs) |
| conversations | same | drop `conversations_external_id_key`; add `UNIQUE (tenant_id, external_id)`; `UNIQUE (tenant_id, id)`; replace `conversations_lead_id_fkey` with `FOREIGN KEY (tenant_id, lead_id) REFERENCES leads (tenant_id, id)` |
| messages | same | composite FK `(tenant_id, conversation_id)` -> conversations; drop `messages_conversation_id_fkey` |
| slots | same | pre-check duplicates (below), then `UNIQUE (tenant_id, start_time)` and `UNIQUE (tenant_id, id)` |
| appointments | same | drop `appointments_slot_id_key`, `appointments_lead_id_key`; add `UNIQUE (tenant_id, slot_id)`, `UNIQUE (tenant_id, lead_id)`; composite FKs to slots and leads; drop `appointments_slot_id_fkey`, `appointments_lead_id_fkey` |
| faq_chunks | same | add index on `(tenant_id)`; no HNSW index exists today (exact scan), so nothing to change for pgvector |
| tool_calls | same | composite FK to conversations; drop `tool_calls_conversation_id_fkey` |
| escalations | same | composite FK; drop `escalations_conversation_id_fkey` |
| events | same | composite FK; drop `events_conversation_id_fkey` |
| llm_calls | **nullable, no default** | Shared with outreach: outreach rows have `conversation_id NULL` and `prospect_id` set. Stamping Summit on those would put an untenanted flow in a tenant (contradicts TEN-06). Decision for planner: `tenant_id uuid REFERENCES tenants(id)` nullable; `_log_llm` writes it; outreach leaves NULL. Composite FK `(tenant_id, conversation_id)` is MATCH SIMPLE so NULLs skip the check. Branch DB currently has 0 rows with NULL conversation_id [VERIFIED], so the live copy may differ. |
| agent_events (new, mig 004) | NOT NULL FK tenants | `id bigserial`, `conversation_id int` (**no FK**, see risk R7), `kind text NOT NULL`, `payload jsonb NOT NULL DEFAULT '{}'`, `created_at`; index `(tenant_id, conversation_id, id)`; triggers: `BEFORE UPDATE OR DELETE ... FOR EACH ROW` and `BEFORE TRUNCATE ... FOR EACH STATEMENT` both `RAISE EXCEPTION 'agent_events is append-only'` |
| eval_runs, eval_results | none | Global harness data; per-pack reports are Phase 5 |
| campaigns, prospects, outreach_messages, suppressions, prospect_events, scrape_runs | none (TEN-06) | Test asserts no `tenant_id` column on this list |

Existing constraint names (needed for `DROP CONSTRAINT`) [VERIFIED: pg_constraint on the branch DB]: `conversations_external_id_key`, `conversations_lead_id_fkey`, `messages_conversation_id_fkey`, `appointments_slot_id_key`, `appointments_lead_id_key`, `appointments_slot_id_fkey`, `appointments_lead_id_fkey`, `tool_calls_conversation_id_fkey`, `escalations_conversation_id_fkey`, `events_conversation_id_fkey`, `llm_calls_conversation_id_fkey`. Use `DROP CONSTRAINT IF EXISTS` and `ADD ... ` guarded with `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname=...)` so a re-run on a half-migrated copy is safe (the runner's per-file transaction already makes each file atomic, so this is belt and braces; keep it cheap).

Slot duplicate pre-check (inside mig 003, before the unique): `DO $$ BEGIN IF EXISTS (SELECT 1 FROM slots GROUP BY start_time HAVING count(*)>1) THEN RAISE EXCEPTION 'duplicate slot start_time; resolve before migrating'; END IF; END $$;` Better a clear failure than a half-applied unique. The branch DB has 40 slots / 40 distinct [VERIFIED]. Appointments referencing a duplicate would make auto-dedup unsafe, so do not auto-dedupe.

After the unique exists, `ensure_slots` may use `ON CONFLICT (tenant_id, start_time) DO NOTHING` in addition to NOT EXISTS (closes the concurrent top-up race); the NOT EXISTS must add `AND s.tenant_id = :t`. The INSERT must set `tenant_id` explicitly.

Other required query edits (D-13 and isolation): `lookup_faq` SQL `WHERE tenant_id = :t ORDER BY embedding <=> ...`; `_faq_keywords` likewise; `seed_faq(tenant_id)`: `SELECT 1 FROM faq_chunks WHERE tenant_id=:t LIMIT 1`, inserts pass `tenant_id`. `faq_seed.sql` (baseline, explicit ids, no tenant column at that point) is fine because migrations backfill the DEFAULT afterwards.

**Sequence fix (mig 001 or 002):** `SELECT setval(pg_get_serial_sequence('faq_chunks','id'), GREATEST((SELECT max(id) FROM faq_chunks), 1))` (use `is_called` correctly: `setval(seq, max)` makes next = max+1; for an empty table skip the call). Without it, a hosted-bootstrapped DB (`faq_seed.sql` ids 1..12, sequence at 1) fails with duplicate key on the first per-tenant insert [VERIFIED: faq_seed.sql has no setval; branch seq is 12 only because seed_faq/initdb ran].

## 3. Migration runner design

Facts that drive the design [VERIFIED: docker-compose.yml, bootstrap.py]:
- Dev/branch compose mounts only `init.sql` and `outreach.sql` into `docker-entrypoint-initdb.d`; a fresh volume therefore already has `public.leads` when the API starts, so today's `to_regclass('public.leads')` guard returns False and **would skip everything** if migrations lived inside the guard.
- Hosted empty DB: no initdb mounts; `bootstrap_schema` runs `init.sql`, `outreach.sql`, `faq_seed.sql`.
- API container sees `./db` at `/srv/db:ro` (`settings.db_dir`), so `db/migrations/` is visible without an image rebuild.
- `exec_driver_sql` with a no-parameter multi-statement string already works under psycopg3 here. Keep migration SQL free of `%` and bind-looking `:name` text. `DO $$ ... $$` blocks are fine.

Design:
```python
# Sketch (not applied)
MIG_LOCK = 724911  # arbitrary constant
def bootstrap_schema(eng=engine) -> bool:
    created = False
    with eng.begin() as c:
        c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIG_LOCK})
        if not c.execute(text("SELECT to_regclass('public.leads')")).scalar():   # guard now covers ONLY the baseline
            for f in ("init.sql", "outreach.sql", "faq_seed.sql"):
                if (settings.db_dir / f).is_file(): _run(c, f)
            created = True
    apply_migrations(eng)          # always, empty / dev-initdb / live copy alike
    return created

def apply_migrations(eng):
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    for f in sorted((settings.db_dir / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
        with eng.begin() as c:                                       # own transaction per file (D-01)
            c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIG_LOCK})
            if c.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": f.stem}).first():
                continue                                             # re-checked under the lock
            _run(c, "migrations/" + f.name)
            c.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": f.stem})
```
Behaviours:
- Empty DB (hosted): baseline then 001..004. Dev fresh volume: initdb did baseline, runner applies 001..004. Live/populated copy with no `schema_migrations`: baseline skipped, 001..004 applied. All converge to the same schema; no "stamp baseline" row is required because 001+ are all post-baseline. [This relies on the live DB being at the `init.sql + outreach.sql` state; verify with a schema diff in section 5.]
- Return value `created` keeps its meaning (log line, main.py ignores it).
- Missing `migrations/` dir: `glob` on a missing dir yields nothing, which silently applies zero migrations in a misconfigured deploy. Fail loudly: raise if the directory does not exist (the only place the file set could silently vanish is a Docker image/mount change).
- Filename ordering: zero-padded 3 digits; lexical sort. Reject gaps? Not needed (YAGNI); a test asserts sorted unique prefixes.
- `bootstrap_schema(eng)` and `apply_migrations(eng)` take the engine as a parameter so tests can run them against a scratch database engine.
- Failure behaviour: exception propagates and the API refuses to start (existing comment in main.py says that is intended); the failed file's transaction rolls back and no `schema_migrations` row is written.
- No checksum column (shortcut: edits to an applied migration are not detected; add a checksum if migrations start being edited after release).
- `CREATE INDEX CONCURRENTLY` and anything non-transactional are not allowed in this design.
- Operator CLI for TEN-01: `docker compose exec api python -c "from app.bootstrap import bootstrap_schema; bootstrap_schema()"` (or just restart api). Optionally `python -m app.bootstrap` with a `__main__` guard (2 lines) so the success criterion "operator can apply migrations" has a named command. Recommended.

## 4. Tests and fixtures touching the DB

Tests run against the real DB (`conftest.py` autouse session fixture) [VERIFIED]. `remove_test_data` deletes rows with `id > first` from conversations and children and then leads/appointments/prospects/campaigns.

Direct `engine` users (all stay valid because `engine` stays exported and the column DEFAULT stamps Summit): test_scrapes.py (13; 48,53,58,92,108,112), test_admin.py (8; 48,64,74,111), conftest.py (5; 17,20), test_outreach.py (12; many), test_agent.py (10; 21,38,66,149,152,170), test_intake.py (6; 46), test_calls.py (11; 24,32,37,70,74,86,125), test_pilot.py (6; 24,54), test_chat_security.py (6; 30). Also `evals/runner.py` and `scripts/seed_demo.py` (section 1).

Needed edits:
- `conftest.py`: add `agent_events` handling to cleanup (R7); add cleanup of non-default tenants and their rows created by new tests (e.g. `DELETE ... WHERE tenant_id <> default` for the tenant tables in dependency order, then `DELETE FROM tenants WHERE slug LIKE 'test-%'`). Keep `CONVO_CHILDREN` in sync (add nothing for agent_events if no FK; handle via trigger-disable below).
- `test_agent.py:23` (`UPDATE slots SET is_booked=false`) and `:150` (`DELETE FROM slots ...`) are global and fine while only Summit exists; scope them to the default tenant if a second tenant's slots are created in the same session.
- `test_agent.py:99,108,114` lambdas for `lookup_faq(query, k=3)`: keep compatible (see section 1).
- `test_calls.py`, `test_admin.py` assert on API payloads that include `SELECT *` rows (`/leads`, `/leads/{id}`): rows will now contain a `tenant_id` uuid string; check serialization (FastAPI handles `uuid.UUID`) and any exact-key asserts. [ASSUMED: not read line by line; grep for exact dict equality when planning.]
- New test files (Wave 0): `test_migrations.py`, `test_tenancy.py`, `test_rls_proof.py`, `test_agent_events.py`, `test_logging_tenant.py`; see Validation Architecture.
- Makefile `test` (line 10) uses plain `docker compose exec api` which targets the **live** stack. Use `$(GCOMPOSE) exec api python -m pytest -q` for this phase (add `g-test` target, 2 lines).

## 5. Proving migrations on a dump of the branch DB

Principles: never use plain `docker compose` (live stack, port 5432); always `-p roofdesk-global` via `$(GCOMPOSE)` or `docker exec roofdesk-global-db-1`; the target is a new database in the **branch** cluster, so no other DB is touched. Dump files go in the session scratchpad, not the repo (synthetic demo data, but treat as data).

```bash
SCR=/private/tmp/claude-501/-Users-ervenderr-Projects-roofdeskai/0c064e05-2147-4d14-9df0-2574595a5952/scratchpad
DB="docker exec -i roofdesk-global-db-1"
# 1. dump (custom format, inside the container so client/server versions match)
docker exec roofdesk-global-db-1 pg_dump -U leadpilot -Fc leadpilot > $SCR/branch.dump
# 2. scratch DBs
$DB psql -U leadpilot -c "CREATE DATABASE leadpilot_mig" -c "CREATE DATABASE leadpilot_empty"
$DB pg_restore -U leadpilot -d leadpilot_mig --no-owner < $SCR/branch.dump
# 3. record pre-state
$DB psql -U leadpilot -d leadpilot_mig -Atc "select 'leads',count(*) from leads union all select 'conv',count(*) from conversations union all select 'slots',count(*) from slots union all select 'faq',count(*) from faq_chunks"
# 4. migrate via the real runner against the scratch DB only (URL override applies to this one command)
URL="postgresql+psycopg://leadpilot:${POSTGRES_PASSWORD:-leadpilot}@db:5432/leadpilot_mig"
$GCOMPOSE exec -e DATABASE_URL="$URL" api python -m app.bootstrap
# 5. idempotency: run step 4 again -> no new schema_migrations rows
# 6. post-state: same counts; every tenant table has 0 NULL tenant_id (llm_calls excepted); composite constraints exist;
#    select version from schema_migrations order by 1
# 7. unit tests + gate on the scratch DB
$GCOMPOSE exec -e DATABASE_URL="$URL" api python -m pytest -q
make eval-gate  # but with the URL override: $GCOMPOSE exec -e DATABASE_URL="$URL" -e GIT_SHA=... api python -m evals.runner --gate
# 8. empty path: same as step 4 with DATABASE_URL pointing at leadpilot_empty (baseline + 001..004 from nothing)
# 9. schema equivalence: pg_dump --schema-only of leadpilot_mig vs leadpilot_empty (and a fresh-volume DB) diff; expect only ordering/oid noise
# 10. cleanup: DROP DATABASE leadpilot_mig; DROP DATABASE leadpilot_empty; rm the dump
```
Notes:
- `settings.database_url` is read from env by pydantic-settings, so `-e DATABASE_URL=...` overrides the compose value for that exec only [VERIFIED: config.py has `database_url: str`; assumes default env-name mapping, confirm with `python -c "from app.config import settings; print(settings.database_url.split('@')[-1])"` which prints no credentials].
- Running pytest/eval on the scratch DB (not the branch DB itself) keeps the branch stack's own data pristine and satisfies D-04. The gate additionally needs a working local LLM (Ollama) from inside the container; the baseline requires local-only models (`assert_local_only`). If Ollama is unreachable the gate cannot be proven here; check first.
- The api container must have the new Python code: rebuild with `make g-up` (compose builds the image; only `./db` is bind-mounted) [ASSUMED: source is baked into the image; `docker inspect` the mounts to confirm].
- Pass criteria per section 2 of success criteria: step 6 counts equal step 3 counts; step 7 94/96 with the same two failing ids (compare to `evals/baselines/v1-roofing.json` using the existing `--gate`).

## 6. Non-owner app role + FORCE RLS proof (scratch DB)

Pattern [CITED: .planning/research/STACK.md; Postgres semantics MEDIUM]: superusers and BYPASSRLS roles skip RLS always; table owners skip unless `FORCE ROW LEVEL SECURITY`; so the app role must be `NOSUPERUSER NOBYPASSRLS` and not the owner. The branch role `leadpilot` is a superuser with Bypass RLS [VERIFIED: `\du`].

Do it as a pytest (`test_rls_proof.py`) so it is repeatable, with a fixture that:
1. Using the superuser engine in autocommit, `CREATE DATABASE rls_probe` (name unique per run) in the branch cluster; builds an engine from `make_url(settings.database_url).set(database="rls_probe")`; runs `bootstrap_schema(eng)` there (the runner taking an engine pays off here).
2. `CREATE ROLE rls_probe_app LOGIN PASSWORD '<generated per run via secrets.token_hex>' NOSUPERUSER NOBYPASSRLS` (roles are **cluster-wide**: use a unique name and `DROP OWNED BY` + `DROP ROLE` in teardown). `GRANT USAGE ON SCHEMA public`; `GRANT SELECT,INSERT,UPDATE,DELETE ON leads, conversations, slots, appointments, faq_chunks, messages TO rls_probe_app`; `GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO rls_probe_app`.
3. For the proof tables: `ALTER TABLE t ENABLE ROW LEVEL SECURITY; ALTER TABLE t FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation ON t USING (tenant_id = current_setting('app.tenant_id', true)::uuid) WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);` The `true` second argument returns NULL when unset, so an unset tenant sees **zero rows** (fail closed) instead of an error.
4. Assertions, connecting as `rls_probe_app`:
   - tenant A tx sees only A rows; B tx only B; no `set_config` -> 0 rows;
   - INSERT with a mismatching `tenant_id` raises (WITH CHECK);
   - after a commit, a reused pooled connection (pool size 1) shows no tenant (transaction-local works);
   - control: the same queries as `leadpilot` (owner/superuser) see all rows -> demonstrates why the role switch is mandatory;
   - control 2: owner non-superuser without FORCE bypasses; with FORCE does not (optional).
5. Teardown: dispose engines, `DROP DATABASE rls_probe WITH (FORCE)` (PG13+), drop role.

Scope: this exists only in the test; the app keeps connecting as `leadpilot` (D-11). Record in the plan that production switch, a separate migration-owner role, and policy creation on real tables are Phase 6. Do not add policies to the real tables in Phase 2 (they would be inert for the superuser anyway and would add risk).

Logging notes (TEN-05, D-14) [VERIFIED: grep]: no `logging.basicConfig`/Formatter exists in `api/app`. Uvicorn does not configure the root logger, so `leadpilot.*` INFO records are currently dropped and WARNING+ go through Python's last-resort handler. So "log format gains `tenant=`" requires introducing logging config (e.g. in `main.py` before app creation: `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s tenant=%(tenant_id)s %(message)s")` with a `TenantFilter` attached to the **handler** (record filters on loggers do not apply to propagated child records; handler filters do). Default value `"-"`. Contextvar set at `handle_turn` entry (not only in `tx()`, since `tools.run` logs outside any tx) and reset in `finally`. Sync FastAPI endpoints run in a threadpool; contextvars are copied into the worker thread per call, so set inside `handle_turn` itself, not in a separate middleware. Check that adding INFO logging does not start printing PII (bodies/emails): current `log.*` calls log ids and exception names only, but audit before enabling INFO globally. `llm` module logger `leadpilot.llm` is also covered.

`agent_events` writes (D-15): `agent.py` turn start (in `handle_turn` after `_open`), `tools.run` (after executing, kind `tool_call`, payload name/ok/latency only, **no args/PII**), `tools.escalate_to_human` (kind `escalation`, reason). Write inside the same `tx` where one is already open, or a fresh `tx(tenant_id)`. Failure to log an event must not break the turn? Decide: wrap in try/except with `log.exception` (never swallow silently), since a logging side-table must not block bookings.

## Common Pitfalls

### P1: Guard skips migrations on dev fresh volume
The initdb mount creates `leads`, so a migration run inside the old `to_regclass` guard never executes. Fix: guard baseline only; always `apply_migrations` (section 3).

### P2: faq_chunks sequence behind explicit ids (hosted bootstrap)
Per-tenant `seed_faq` collides with ids 1..12. `setval` in migration 001/002 (section 2).

### P3: Unique on slots(start_time) fails on live data
No such unique exists today; concurrent `ensure_slots` could have created duplicates on the real live DB. Pre-check with a clear error; run the check against a fresh dump of the *live* DB (read-only dump), not just the branch DB, before ever touching live.

### P4: DEFAULT hides missed call sites
Anything that forgets `tenant_id` silently writes Summit. Add a test that creates a second tenant, runs one full `handle_turn(..., tenant_id=B)` against a stubbed LLM, and asserts every tenant-table row created has `tenant_id = B` (leads, conversations, messages, tool_calls, llm_calls, events, escalations, agent_events).

### P5: `tools.run(cid, name, args, fn)` splats `fn(**args)`
Tenant must not travel in model-supplied `args`; bind it via `functools.partial` at call sites in `agent.py` so a model cannot choose a tenant. (Tool args are already model-controlled for `lead_id`, `slot_id`: with composite FKs, a cross-tenant `lead_id`/`slot_id` now fails at the DB. Also add `AND tenant_id = :t` to `book_appointment`, `update_lead` WHERE clauses.)

### P6: Cross-tenant id lookups
Conversation, lead and slot ids stay global serials. `token_matches(cid, token)` and `_open(cid)` must filter by tenant (`WHERE id=:i AND tenant_id=:t`) so a tenant cannot continue another tenant's conversation by id. The token check already protects /chat; inbound path uses `external_id` only.

### P7: Module-level state
`ensure_slots`/`seed_faq` have no module cache today [VERIFIED], but `SLOT_HOURS`/`SLOT_DAYS_AHEAD` constants stay roofing until Phase 3 (D-12); do not add tenant-dependent caching now.

## Risks (summary)

| # | Risk | Mitigation |
|---|------|------------|
| R1 | Live demo DB broken by migration | Branch/scratch only; read-only dump of live for a final dry run; take a live `pg_dump` backup before any later live apply (ask the user first, outward-facing) |
| R2 | Duplicate slots block unique | Pre-check with explicit error |
| R3 | faq sequence collision | setval in 001 |
| R4 | llm_calls shared with outreach | tenant_id nullable (decision needed) |
| R5 | Missed INSERT sites stamp Summit | P4 test; explicit tenant_id in all tenant INSERTs |
| R6 | psycopg multi-statement/`%`/`:` in SQL files | No binds in migrations; `exec_driver_sql`; DO blocks use `$$` only |
| R7 | `agent_events` append-only vs test cleanup | No FK to conversations; conftest cleanup uses `ALTER TABLE agent_events DISABLE TRIGGER USER` ... `ENABLE TRIGGER USER` in one transaction as superuser (Phase 6 non-owner app role cannot do this, which is the intent) |
| R8 | Gate depends on local Ollama | Check availability before planning gate tasks; fall back to subset runs, document in plan |
| R9 | evals `reset_db` is global | Tenant-filter now (cheap: `WHERE tenant_id = :t`) or flag for Phase 5 |
| R10 | `SELECT *` admin payloads gain `tenant_id` | Check tests and n8n consumers; harmless extra field |
| R11 | Host `make test` hits live stack | use `$(GCOMPOSE)` |
| R12 | Composite FK drops old FKs; if a migration is partially edited later | Per-file tx + IF EXISTS guards |

## Code Examples (migration shape)

```sql
-- 002_tenant_columns.sql (sketch)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL
  DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
-- repeat for conversations, messages, slots, appointments, faq_chunks, tool_calls, escalations, events
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES tenants(id);
UPDATE llm_calls l SET tenant_id = c.tenant_id FROM conversations c WHERE l.conversation_id = c.id AND l.tenant_id IS NULL;
```

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| nullable add + batched backfill + SET NOT NULL | `ADD COLUMN NOT NULL DEFAULT const` (PG11+, metadata only) | One step, same end state as D-03 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default tenant uuid value `0000...0001` is acceptable | 2 | Cosmetic; D-05 only demands a fixed constant |
| A2 | `DATABASE_URL` env var overrides `settings.database_url` | 5 | Proof commands would hit the branch DB; verify with the credential-free print first |
| A3 | API source is baked into the image (rebuild needed after code change) | 5 | Extra/less rebuild step |
| A4 | Exact-key asserts in test_admin/test_calls not affected by new `tenant_id` field | 4 | Minor test edits |
| A5 | Postgres RLS/FORCE/set_config semantics as described (not re-fetched) | 6 | Caught by the proof test itself |
| A6 | llm_calls.tenant_id nullable is the right call for shared outreach rows | 2 | Needs user/planner confirmation |
| A7 | The live (non-branch) DB schema equals init.sql + outreach.sql state | 3 | Migration could fail on an unexpected column; schema-diff the live dump read-only before first live apply |

## Open Questions

1. **llm_calls tenancy** - recommendation: nullable `tenant_id`, outreach NULL (A6).
2. **Does Ollama run inside the branch stack for the gate?** Check before sizing gate tasks (R8).
3. **Which hosted deploy exists?** `faq_seed.sql` path matters only there; the sequence fix is harmless either way.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | stack | yes | - | - |
| Branch stack (project roofdesk-global) | proofs | yes (db 55432, api, n8n, mailpit up) | PG 16.15 pgvector | `make g-up` |
| psql / pg_dump on host | optional | yes (/opt/homebrew/bin) | version not checked vs server 16 | use `docker exec ... pg_dump` (recommended) |
| Ollama / local LLM for gate | eval gate | not checked | - | subset gate; see R8 |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (run inside the api container) |
| Config file | none found (conftest in `api/app/`) |
| Quick run command | `make g-up` then `docker compose -p roofdesk-global -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.global.yml exec api python -m pytest -q api/app/test_tenancy.py api/app/test_migrations.py` (paths relative to container workdir; confirm) |
| Full suite command | `$(GCOMPOSE) exec api python -m pytest -q` then `make eval-gate` |

### Phase Requirements -> Test Map
| Req | Behavior | Type | Command / file | Exists |
|-----|----------|------|----------------|--------|
| TEN-01 | runner applies 001..004 on empty and populated scratch DBs, idempotent | integration | `test_migrations.py` (scratch DB fixture) + section 5 manual dump proof | Wave 0 |
| TEN-02 | two tenants share slot start_time and external_id; same tenant duplicates still rejected; cross-tenant FK rejected | integration | `test_tenancy.py` | Wave 0 |
| TEN-03 | `tx()` sets `app.tenant_id`, resets after commit on pooled conn; bad uuid raises; grep-style test: no `engine.begin()/connect()` in tenant modules | unit | `test_tenancy.py` | Wave 0 |
| TEN-04 | `ensure_slots(B)` creates rows although A has them; `seed_faq(B)` seeds although A has rows; `lookup_faq` only returns own tenant | integration | `test_tenancy.py` (stub embeddings) | Wave 0 |
| TEN-05 | log record carries `tenant=<id>` during `handle_turn`; `agent_events` rows written; UPDATE/DELETE/TRUNCATE raise | unit/integration | `test_logging_tenant.py`, `test_agent_events.py` | Wave 0 |
| TEN-06 | no `tenant_id` column on campaigns, prospects, outreach_messages, suppressions, prospect_events, scrape_runs; existing outreach/pilot tests still pass | integration | `test_tenancy.py` + existing `test_outreach.py`, `test_pilot.py` | partly exists |
| D-11 | non-owner role + FORCE RLS isolates tenants, fails closed, superuser bypass shown | integration | `test_rls_proof.py` | Wave 0 |
| D-16 | roofing 94/96 same two failures | gate | `make eval-gate` | exists |

### Sampling Rate
- Per task commit: the new targeted test file(s) plus `test_agent.py`.
- Per wave merge: full pytest on the branch stack.
- Phase gate: full pytest + full `make eval-gate` + section 5 dump proof green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `api/app/test_migrations.py`, `test_tenancy.py`, `test_agent_events.py`, `test_logging_tenant.py`, `test_rls_proof.py`
- [ ] Shared fixture `scratch_db` (create/drop database from the superuser engine) in `conftest.py`
- [ ] `conftest.py` cleanup for non-default tenants and agent_events (R7)
- [ ] `g-test` Makefile target

## Security Domain

Applicable ASVS: V4 access control (tenant isolation by composite FK now, RLS in Phase 6), V5 input validation (uuid parse in `tx()`, no f-string SQL with tenant values; keep binds), V7 logging (no PII in `agent_events.payload` or tenant log lines).

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Cross-tenant read via guessed ids | Info disclosure | tenant filter in `_open`/`token_matches`/tool queries + composite FKs; RLS later |
| Tenant chosen by model tool args | Tampering | bind tenant outside `args` (P5) |
| Pooled connection leaking tenant | Info disclosure | transaction-local `set_config`; tested |
| Tampering with audit trail | Repudiation | append-only trigger (superuser can still disable; Phase 6 non-owner role cannot) |
| Test role/password leaks | Info disclosure | generated per run, never printed, dropped in teardown |

## Sources

### Primary (HIGH)
- Repository reads: `db/init.sql`, `db/outreach.sql`, `db/faq_seed.sql`, `api/app/{db,bootstrap,faq,tools,agent,admin,main,pilot,config,conftest}.py`, `evals/runner.py`, `scripts/seed_demo.py`, `docker-compose.yml`, `docker-compose.global.yml`, `Makefile`, `.planning/{ROADMAP,REQUIREMENTS}.md`, `02-CONTEXT.md`
- Live branch DB inspection via `docker exec roofdesk-global-db-1 psql` (read-only): tables, constraints, role attributes, row counts, sequence value

### Secondary (MEDIUM)
- `.planning/research/STACK.md` (RLS, `set_config`, migrations, role guidance)

### Tertiary (LOW)
- Postgres RLS/FORCE/`ADD COLUMN DEFAULT` behaviour from training knowledge; verified by the section 5/6 proofs rather than docs.

## Metadata

**Confidence:** call-site inventory HIGH; DDL plan HIGH; runner design HIGH; RLS proof MEDIUM; logging/contextvar details MEDIUM (uvicorn logging behaviour from training knowledge).
**Research date:** 2026-11-03. **Valid until:** 30 days (repo changes faster than the domain).
