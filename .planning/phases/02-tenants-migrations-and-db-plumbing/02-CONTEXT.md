# Phase 2: Tenants, Migrations and DB Plumbing - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning
**Mode:** --auto (recommended defaults chosen, logged below)

<domain>
## Phase Boundary

Make the database multi-tenant ready with no behaviour change for Summit Roofing: numbered SQL migrations with a `schema_migrations` table, a `tenants` table with a seeded default tenant, `tenant_id` plus composite uniques/FKs on tenant tables, one `db.tx(tenant_id)` helper for all tenant data access, tenant-aware slot generation and FAQ seeding, tenant-stamped logs and an append-only `agent_events` table. Outreach, replies, pilot and `/intake` (RoofDesk's own sales funnel) stay untenanted. RLS enforcement, per-tenant keys and dropping the default are Phase 6.

</domain>

<decisions>
## Implementation Decisions

### Migrations
- **D-01:** [auto] Numbered files `db/migrations/NNN_name.sql`, applied in order by a small runner in `bootstrap.py`, each in its own transaction, recorded in `schema_migrations(version, applied_at)`. No Alembic.
- **D-02:** [auto] `init.sql` stays the baseline for an empty DB (schema as of `v1-roofing`); migrations run after it on every start, so fresh and live DBs converge. Migration 001 creates `tenants`; later ones add columns.
- **D-03:** [auto] Expand/contract: `tenant_id` is added nullable, backfilled to the default tenant, then set NOT NULL with a column DEFAULT of the default tenant id (so unmodified code keeps working). The DEFAULT is dropped in Phase 6, not here.
- **D-04:** [auto] Proven on a copy of a populated DB (dump from the branch stack, restore to a scratch DB, migrate, run unit tests plus the gate), never on the live volume.

### Tenant model
- **D-05:** [auto] `tenants(id uuid pk, slug unique, name, timezone, pack_slug, created_at)`. Default tenant: slug `summit-roofing`, fixed uuid constant in config, timezone `America/Denver`.
- **D-06:** [auto] `tenant_id` goes on leads, conversations, slots, appointments, faq_chunks and the per-conversation tables worth filtering directly (messages, tool_calls, llm_calls, escalations, events). Child tables carry it too so Phase 6 RLS policies are simple, with composite FKs `(tenant_id, id)` where cheap.
- **D-07:** [auto] Uniques become composite: `slots(tenant_id, start_time)`, `conversations(tenant_id, external_id)`, `appointments(tenant_id, slot_id)` and `(tenant_id, lead_id)`.
- **D-08:** [auto] Outbound tables (`outreach.sql`: prospects, campaigns, drafts, replies, pilot) get no `tenant_id` (TEN-06). A test asserts this.

### db.tx() helper
- **D-09:** [auto] `db.tx(tenant_id)` is a context manager over `engine.begin()` that runs `SELECT set_config('app.tenant_id', :t, true)` first. A separate `db.system()` is the explicit untenanted context (bootstrap, outreach, pilot, admin cross-tenant). Every `engine.begin()` call site in tenant code moves to `tx()`; the call site inventory is part of plan 1 research.
- **D-10:** [auto] `tenant_id` is passed explicitly down the call chain (`handle_turn`, tools, faq) with the default tenant as the parameter default for now; no contextvar magic.
- **D-11:** [auto] The app role today is the compose Postgres superuser, so RLS would do nothing. Phase 2 only records this in the plan and adds the non-owner `app` role plus FORCE RLS on a test database to prove the pattern; the production switch is Phase 6.

### Slots and FAQ
- **D-12:** [auto] `ensure_slots(tenant_id)` checks NOT EXISTS per tenant. Slot hours stay the roofing constants until Phase 3 moves them to the pack.
- **D-13:** [auto] `seed_faq(tenant_id)` early-returns only if that tenant already has rows; reload is delete-then-insert per tenant. `lookup_faq` filters by tenant_id in the SQL.

### Logging and events
- **D-14:** [auto] A `logging.Filter` adds `tenant_id` to records from a contextvar set inside `db.tx()` callers/request middleware; log format gains `tenant=%(tenant_id)s`.
- **D-15:** [auto] `agent_events(id, tenant_id, conversation_id, kind, payload jsonb, created_at)` is append-only (no UPDATE/DELETE grant intent, documented; trigger blocks UPDATE/DELETE). Written for turn start, tool call, escalation. The existing `events` table stays as is.

### Regression gate
- **D-16:** [auto] Every plan ends with `make g-test` and a `make eval-gate` run (subset allowed mid-phase, full run before phase verification). Roofing must stay 94/96 with the same two failures.

### Claude's Discretion
Migration file naming details, exact set of child tables getting composite FKs, test layout.

</decisions>

<canonical_refs>
## Canonical References

- `RoofDesk Global Platform Spec.md` (/Users/ervenderr/Downloads/) — migration steps 2 and tenancy sections
- `.planning/ROADMAP.md` — Phase 2 goal and success criteria
- `.planning/REQUIREMENTS.md` — TEN-01..TEN-06
- `.planning/research/STACK.md` — RLS, `set_config`, migrations, role guidance
- `.planning/research/PITFALLS.md` — pitfalls 1, 3, 4 (RLS bypass, default tenant, retrofit misses)
- `.planning/research/ARCHITECTURE.md` — tenant_id passing, untenanted modules
- `.planning/phases/01-baseline-freeze-and-environment-isolation/01-ROOFING-INVENTORY.md` — hidden coupling list
- `db/init.sql`, `db/outreach.sql`, `db/faq_seed.sql`, `api/app/db.py`, `api/app/bootstrap.py`, `api/app/tools.py`, `api/app/faq.py`, `api/app/admin.py`
- `Makefile` (`g-up`, `g-test`, `eval-gate`), `docker-compose.global.yml`, `evals/baselines/v1-roofing.json`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bootstrap.bootstrap_schema()` — runs init/outreach/faq_seed on an empty DB; extend with the migration runner.
- `evals/runner.py --gate` and `make eval-gate` — regression check.
- `docker-compose.global.yml` stack on port 55432 for a safe DB.

### Established Patterns
- Raw SQL via `sqlalchemy.text` and `engine.begin()` (about 62 references across 20 files); `db.py` is 5 lines.
- Multi-statement SQL files run with `exec_driver_sql`.

### Integration Points
- `tools.ensure_slots`, `faq.seed_faq`, `agent.handle_turn`, `main.py` startup, `admin.py` metrics (global today).
- Tests use the real DB via `conftest.py`.

</code_context>

<specifics>
## Specific Ideas

No specific requirements, open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- Per-tenant API keys, RLS enforcement in the running app, dropping the default tenant — Phase 6
- Moving slot hours/timezone into the pack — Phase 3
- Tenant-scoped admin metrics endpoints — Phase 6 (SEC-05)

</deferred>

---

*Phase: 02-tenants-migrations-and-db-plumbing*
*Context gathered: 2026-11-03*
