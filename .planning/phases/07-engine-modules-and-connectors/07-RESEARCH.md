# Phase 7: Engine Modules and Connectors - Research

**Researched:** 2026-11-04
**Domain:** Deterministic business modules (quote, capacity, connectors/brief, review reply, intake) on a FastAPI + Postgres RLS multi-tenant codebase
**Confidence:** HIGH on integration (read from the actual code), MEDIUM on heuristics that need fixture tuning (review "unknown-fact" check, quote-text number extraction)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pack extensions (shared)**
- **D-01:** Add optional pack files `services.yaml`, `capacity.yaml`, `connectors.yaml`, plus optional `reviews:`/`intake:` blocks, loaded by the existing Pydantic loader (`extra="forbid"`, `PackError` naming file+field, hash includes them). Absent file = module disabled for that tenant (endpoint returns 404 "module not enabled"). Roofing and dental packs get no new files (roofing agent keeps refusing chat prices; 94/96 untouched).
- **D-02:** Module tests/evals need a pack that uses them. Create a small synthetic fixture pack `api/app/tests_data/packs/demo-venue/` (services with group/corporate rules, rota/capacity, connectors, intake mapping). Phase 10 promotes the idea to the real third pack; do not build it here.
- **D-03:** Engine modules live in `api/app/engine/` as pure functions of `(pack, input)` returning frozen dataclasses/Pydantic models; DB access and routes stay in thin route modules. No `settings.default_tenant_id`; tenant always explicit via `require_tenant`.

**Quote builder (MOD-01, MOD-02)**
- **D-04:** `Decimal` only; services have `id`, `name`, `unit` (per_person/flat/per_hour), `price`, optional `min_qty`, `add_ons`, and `rules` (group tier discounts, corporate surcharge as percentages/fixed). Total quantized once at the end; currency from the pack.
- **D-05:** Missing price, unknown service, qty below min, or a rule that cannot be evaluated returns a typed `NeedsHuman(reason, missing=[...])`; never a guess. Request input is structured (`service_id`, `qty`, `add_on_ids`, `customer_type`); the LLM may extract fields from an email but only validated structured input reaches the builder.
- **D-06:** New tenant-scoped `drafts` table (migration 007, RLS + grants like Phase 6): `id, tenant_id, kind (quote|review_reply), status (pending|approved|rejected|needs_human|sent), payload jsonb, input_hash, created_at, decided_at`. Quote draft payload stores computed line items + total + model-written email text. Approve/reject endpoints. The existing outreach approval queue stays untenanted and untouched.
- **D-07:** Quote email text is validated against the computed quote (every number in the text must equal the quote total/line prices; no other currency amounts) instead of the roofing `_CLAIM_RE` price-claim regex; failure -> regenerate once -> `needs_human`. Quote drafts are never auto-sent.

**Capacity checker (MOD-03)**
- **D-08:** `capacity.yaml` defines shifts (name, weekday/time window in tenant tz) with `min_staff`, `max_covers_per_staff` (or resource capacity), and rota (staff per shift). Checker compares bookings (appointments/bookings table or the bookings connector) per shift and returns flags `over_capacity|understaffed|under_utilised` with a stable `flag_key`.
- **D-09:** Flags persisted in `capacity_flags` (tenant-scoped, RLS): unique `(tenant_id, flag_key)` + `input_hash`; re-running with unchanged inputs creates nothing new (dedupe); changed inputs update and set `reflagged_at` and return as "re-flagged". Resolved flags clear when inputs fix them.
- **D-10:** All time math in `zoneinfo` tenant tz with UTC storage; tests cover spring-forward and fall-back days for America/Denver and Europe/Zurich.

**Connector layer (MOD-04, MOD-05)**
- **D-11:** One `Connector` Protocol (`name`, `fetch(tenant, day) -> ConnectorResult`) with mock adapters `sheet`, `accounting`, `bookings`, `ads`. Mock data is deterministic (seeded by tenant slug + date), and every result carries `source="mock"`; any output rendering it labels it "(mock data)". A connector may raise/return `unavailable`; the brief shows "source unavailable" explicitly, never omits silently. Adapter classes are plain, MCP-wrappable later (EXT-02).
- **D-12:** `connectors.yaml` lists enabled sources per tenant. Daily brief (`POST /daily-brief` + `POST /daily-brief/due`): merges connector data into a one-page text/HTML summary, in tenant-local time; `due` returns tenants whose local hour matches the configured send hour and not yet sent that day (state in a `brief_runs` table, tenant-scoped). Disagreement check: the same metric reported by two sources (e.g. bookings count in `bookings` vs `sheet`) differing beyond tolerance is flagged with both numbers. Brief numbers are code-computed; any prose is templated, no LLM required (optional LLM polish out of scope).

**Review responder (MOD-06)**
- **D-13:** `POST /reviews/draft` takes `{review_text, rating, platform}`; LLM drafts in the pack tone (`reviews:` block: tone, signature, forbidden topics). Deterministic post-check `check_reply(text, pack)` blocks: refund/discount/compensation offers, fault admission, unknown-fact claims (reuse grounding-style check against pack facts), and PII (email/phone/address patterns, plus health-privacy language for dental: no confirming someone was a patient). Fail -> regenerate once -> status `needs_human`; pass -> `pending` draft. Never auto-posted; no sentiment gating (all ratings treated the same path).

**intake_event (MOD-07)**
- **D-14:** `POST /intake_event` (name chosen to avoid the untenanted `/intake`) with tenant key. Pack `intake:` block maps source payload fields (`waiver|checkin|result`) via simple dotted-path mapping to `person_key` (email/phone/external id), name, and event fields. Table `intake_people` unique `(tenant_id, person_key)` with `waiver_at/checkin_at/result jsonb`; repeated events upsert, one row per person; processed twice -> same single record (idempotent). Unmapped/invalid payload -> 422 naming the field; no PII in logs (log ids only).

**Evals (EVAL-05)**
- **D-15:** Each module gets a deterministic eval set under `evals/modules/<module>/*.yaml` and a runner `python -m evals.modules [--module X]` that needs no LLM (review responder evals feed fixed drafts to the post-check; quote/capacity/brief/intake are pure). Runs in pytest too. Existing 94/96 roofing and 43/43 dental gates run once at the end of the phase as regression; module eval sets must all pass (they are deterministic, so 100%).

### Claude's Discretion
- File/module naming under `api/app/engine/`, exact table column details, mock data shapes, HTML vs text brief format, endpoint path names beyond those above, plan split (expect ~7-8 sequential plans: pack extension + drafts/migrations, quote, capacity, connectors+brief, review responder, intake_event, module evals + gates).

### Deferred Ideas (OUT OF SCOPE)
- n8n workflows for these modules and the `/admin/tenants`-driven scheduling loop (Phase 8)
- MCP exposure of connectors, Anthropic provider, real venue pack (Phase 10)
- Supplier-order workflow (v2, cut first); real connectors/write actions (v2)
- Generated SOPs and data map for these modules (Phase 9)

### Open items carried in (from CONTEXT)
- Confirm "call 144" Swiss emergency number (Phase 5).
- Deploy needs `PUBLIC_DEMO_TENANT_ID` and `APP_DATABASE_URL` (Phase 6); new tables must follow the Phase 6 RLS/grant pattern (migration 007+; `assert_rls_enforced` coverage check should include new tables).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MOD-01 | Quote builder: request + `services.yaml` -> line items and Decimal total; missing price asks/escalates | Section 3 (Decimal rules, `NeedsHuman`, YAML-float trap) |
| MOD-02 | Quote drafts go to approval queue, validated against computed quote | Sections 2, 3 (`drafts` table, `check_quote_text`) |
| MOD-03 | Capacity checker, dedupe + re-flag, DST-safe | Section 4 (flag_key/input_hash, UTC window math, verified DST instants) |
| MOD-04 | Connector interface + mock adapters labelled as mock | Section 5 |
| MOD-05 | Daily brief in tenant-local time, disagreement flags, "source unavailable" | Section 5 (`due` semantics, tolerance) |
| MOD-06 | Review responder drafts only; deterministic post-check; regenerate once; `needs_human` | Section 6 |
| MOD-07 | `intake_event` webhook, one idempotent record per person | Section 7 |
| EVAL-05 | Per-module deterministic eval sets that pass | Section 8 |
</phase_requirements>

## Summary

Phase 7 adds five pure engine modules plus thin tenant-key routes. No new packages: everything is stdlib (`decimal`, `zoneinfo`, `hashlib`, `re`, `dataclasses`) plus the existing pydantic 2, pyyaml 6, SQLAlchemy 2, FastAPI, and `llm.chat` chain. `tzdata==2026.6` is already in `api/requirements.txt` [VERIFIED: grep of api/requirements.txt]. The existing code gives every seam needed: `pack.py` (frozen `extra="forbid"` models, `_parse`, hash over all non-`scenarios` files), `db.tx(tenant)` (app_rw + transaction-local `set_config`), `auth.require_tenant`/`require_scope`, `db.record_event`, and the Phase 6 RLS migration template.

Roofing/dental stay untouched by construction: the pack hash is a sha256 over file bytes, and Phase 7 adds no files to either pack, so their hashes cannot change. Current values (computed read-only this session by replicating `pack_hash`): summit-roofing `ead72d1bc518723c...`, bright-smile-dental `8431b23718c15834...` (first 16 hex chars) [VERIFIED: local python run]. Pin the full hashes in a test so any accidental edit to a roofing/dental pack file fails loudly. The only shared-code changes that touch the agent path are optional additions to `pack.py` (new `None`-default fields) and, if chosen, one additive keyword on `policy.answer_supported`; both are behavior-neutral for existing callers.

Three non-obvious traps shape the design and are covered below: (1) YAML 1.1 `safe_load` turns `17:00` into the int 1020 and `35.10` into a float, so money and times must be validated through `BeforeValidator`s that demand strings; (2) FastAPI serialises `Decimal` to JSON float/int, so API/DB money must be emitted as strings; (3) migration 007 must be final when first applied, because `apply_migrations` skips applied versions without checksums, so a later edit silently never reaches the dev DB.

**Primary recommendation:** One migration `007_engine_modules.sql` for all four tables, written and RLS-tested in Plan 02; all module logic pure in `api/app/engine/`; every route under `Depends(require_tenant)` with a `require_module` 404 guard; evals under `evals/modules/` driven by one loader reused by pytest.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Quote computation | API / Backend (pure `engine/quote.py`) | — | Code computes numbers; model only writes text |
| Quote email text + extraction | API / Backend (`llm.chat`) | — | Model output always re-validated by code |
| Draft approval queue | Database (`drafts`, RLS) | API (routes) | Tenant-scoped state; approve/reject are guarded UPDATEs |
| Capacity flags + dedupe | Database (unique key) | API (pure checker) | Dedupe enforced by unique constraint, classified in code |
| Connector fetch | API / Backend (plain classes) | — | MCP-wrappable later (EXT-02) |
| Brief schedule ("due") | API / Backend | n8n (trigger only, Phase 8) | "API decides, n8n triggers" constraint |
| Review post-check | API / Backend (pure `check_reply`) | — | Deterministic gate on model output |
| Intake mapping/upsert | API / Backend | Database (unique + upsert) | Idempotency by `UNIQUE (tenant_id, person_key)` |
| Tenant isolation | Database (RLS FORCE) | API (`require_tenant`) | Phase 6 pattern |

## Standard Stack

### Core (all already in the repo; no installs)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.x (existing) | Pack models, request DTOs, `BeforeValidator` for money/time strings | Already the pack loader mechanism [VERIFIED: api/app/pack.py] |
| pyyaml | 6.* (`safe_load`) | Pack + eval YAML | Existing |
| `decimal` | stdlib | Money; `ROUND_HALF_UP`, `Decimal.quantize` | Locked D-04 |
| `zoneinfo` + `tzdata==2026.6` | stdlib + existing pin | Tenant-local time math | `tzdata` already pinned [VERIFIED: api/requirements.txt] |
| SQLAlchemy 2 `text()` + `db.tx` | existing | Tenant-scoped SQL | Phase 6 pattern |
| `hashlib`/`json` | stdlib | `input_hash` over canonical JSON | Deterministic dedupe keys |
| `random.Random(str_seed)` | stdlib | Seeded mock data | String seeds are deterministic across processes (unlike `hash()`) [ASSUMED: CPython seeding behaviour; add a test that two processes agree, or use sha256 -> int seed to remove doubt] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-module migrations | One `007` for all 4 tables | Chosen one-file: RLS catalog/INSERT test additions happen once; schema is firm. A later fix is a new `008`, never an edit |
| Rule DSL (json-logic) | Pydantic discriminated union + dispatch dict | Already decided in STACK.md |
| jinja2 for brief | f-strings / `str.format` | Brief is ~10 lines; no new dependency |

**Installation:** none. **Package Legitimacy Audit:** no new external packages are introduced in this phase; slopcheck not applicable. All names above are already pinned in `api/requirements.txt`.

## Architecture Patterns

### System Architecture Diagram

```
HTTP (X-API-Key) ──> require_tenant ──> tenant_id (from key only)
        │                                    │
        │                          get_pack(tenant_id) ──> Pack (frozen; optional services/capacity/connectors/reviews/intake)
        │                                    │                 │
        │                          require_module(pack,"x") ─> 404 "module not enabled" if None
        ▼
 ┌──────────────┬───────────────┬──────────────┬───────────────┬────────────────┐
 │ POST /quotes │ POST /capacity│ POST /daily- │ POST /reviews │ POST           │
 │              │ /check        │ brief, /due  │ /draft        │ /intake_event  │
 └──────┬───────┴──────┬────────┴──────┬───────┴───────┬───────┴────────┬───────┘
        ▼              ▼               ▼               ▼                ▼
  [LLM extract?]   bookings:       connectors      llm.chat draft   map dotted paths
  validate         body or         .fetch(ctx,day) ──> check_reply   validate / normalise
  QuoteRequest     bookings        ×N sources      fail? regen once  person_key
        ▼          connector       ▼               fail? needs_human      ▼
  build_quote ──>  check_capacity  merge+disagree  pending draft     UPSERT intake_people
  Quote|NeedsHuman (UTC windows)   tenant-local                       (ON CONFLICT)
        ▼              ▼           text/HTML            ▼
  llm email text   classify vs     brief_runs      drafts row (RLS)
  check_quote_text capacity_flags  (tenant,date)   pending|needs_human
  regen once       (new/unchanged/
        ▼          reflagged/resolved)
  drafts row (RLS)
        └──── POST /drafts/{id}/approve|reject  (never sends, never posts)
```

### Recommended Project Structure
```
api/app/
├── engine/
│   ├── __init__.py
│   ├── quote.py          # QuoteRequest, Quote, NeedsHuman, build_quote (pure, Decimal)
│   ├── quote_text.py     # extract_amounts, check_quote_text (pure)
│   ├── capacity.py       # shift_windows, check_capacity, classify_flags (pure)
│   ├── connectors.py     # Connector Protocol, ConnectorResult, 4 mock adapters, registry
│   ├── brief.py          # build_brief, find_disagreements, render_text, is_due (pure)
│   ├── pii.py            # EMAIL_RE, PHONE_RE, ADDRESS_RE (Phase 9 mask() will import these)
│   ├── reviews.py        # check_reply, draft flow helpers (pure check; llm flow thin)
│   └── intake.py         # get_path, normalise_event, merge (pure)
├── drafts.py             # drafts router + create_or_get_draft helper (RLS tx)
├── quotes.py, capacity_routes.py, brief_routes.py, reviews_routes.py, intake_event_routes.py
└── tests_data/packs/demo-venue/*.yaml
db/migrations/007_engine_modules.sql
prompts/quote-extract.v1.md, quote-email.v1.md, review-reply.v1.md
evals/modules/{__init__,__main__,loader}.py + {quote,capacity,brief,reviews,intake}/cases.yaml
```
Note: `api/app/intake.py` already exists (RoofDesk's own sales funnel, untenanted). New route file is `intake_event_routes.py` and the pure module is `engine/intake.py` (different package path, no collision).

### 1. Pack model extension (answers Q1)

**Mechanism.** Keep `FILES` (required, unchanged) and add:
```python
OPTIONAL_FILES = {"services": Services, "capacity": Capacity, "connectors": Connectors}

def _parse_optional(path: Path, model):
    return _parse(path, model) if path.exists() else None   # absent = module disabled; present-but-bad = PackError
```
In `load_pack`: `opt = {n: _parse_optional(root / f"{n}.yaml", m) for n, m in OPTIONAL_FILES.items()}`; add `services/capacity/connectors: ... | None = None` to `Pack`. An empty file yields `None` from `safe_load` and `_parse` already raises `PackError: path: (root): Input should be a valid dictionary` [VERIFIED: pack.py `_parse` loc handling], so "present but empty" is an error, not a silent disable.

**`reviews:` / `intake:` blocks.** Add as optional fields on `PackMeta` (`reviews: Reviews | None = None`, `intake: Intake | None = None`), i.e. top-level keys in `pack.yaml`. PackMeta is `extra="forbid"`, so a roofing `pack.yaml` without these keys validates unchanged and typos fail. Expose via `pack.meta.reviews` / `pack.meta.intake` (do not duplicate onto `Pack`). `python -m app.pack` summary stays valid.

**Hashing.** `pack_hash` already hashes every file except `scenarios/` by relative path + bytes, so new files and new blocks change the hash of *that* pack only. Nothing to change. Roofing/dental hashes cannot move unless a file in their folder is edited. Add a regression test pinning the full sha256 for both (capture with `python -m app.pack` or the replicated snippet in Wave 0; first 16 chars today: roofing `ead72d1bc518723c`, dental `8431b23718c15834`) plus `load_pack("summit-roofing").services is None` etc.

**Loader base dir.** Fixture pack lives in `api/app/tests_data/packs/`, not `businesses/`. Add `load_pack(slug, base: Path | None = None)` (`root = (base or settings.businesses_dir) / slug`). Default behaviour is byte-identical. pytest HTTP tests monkeypatch `settings.businesses_dir` to a tmp dir holding copies of `summit-roofing` (if needed) and `demo-venue` (`shutil.copytree`; do not symlink: `rglob` does not recurse symlinked dirs on 3.12 [ASSUMED]) as `test_pack.py::biz` already does. The eval runner passes `base=` directly.

**Models (all `M` = frozen, `extra="forbid"`).**
```python
def _money(v):  # YAML gives float for 35.10 and int for 35: both must become exact Decimals
    if isinstance(v, bool) or v is None: raise ValueError("money must be a quoted decimal string")
    if isinstance(v, float): raise ValueError('money must be a quoted string like "35.10" (YAML floats lose precision)')
    d = Decimal(str(v))  # raises InvalidOperation -> ValueError subclass handling via try/except
    if not d.is_finite() or d < 0 or d.as_tuple().exponent < -2: raise ValueError("money: >= 0, at most 2 decimals")
    return d
Money = Annotated[Decimal, BeforeValidator(_money)]
Percent = Annotated[Decimal, BeforeValidator(_pct)]   # 0 < p <= 100, same string/int rule
HHMM = Annotated[time, BeforeValidator(_hhmm)]        # str "17:00" only; int (YAML sexagesimal 17:00 -> 1020) rejected with 'quote the time'
```
Rejecting floats outright (rather than `Decimal(str(float))`) is deliberate: it forces `"35.10"` in the YAML and removes any dependence on pydantic's float->Decimal conversion path [ASSUMED: pydantic-core float handling]. Verified this session that `yaml.safe_load` is the loader in use; the 17:00 sexagesimal behaviour is YAML 1.1 standard behaviour that the safe loader applies [ASSUMED: PyYAML not importable on host python here, so not re-run; planner should include a unit test `load` of an unquoted `17:00` expecting `PackError`].

`services.yaml`:
```yaml
currency: CHF
services:
  - id: escape_room            # [a-z][a-z0-9_]*, unique
    name: Escape room
    unit: per_person           # per_person | flat | per_hour
    price: "35.00"             # omit or null => NeedsHuman(missing_price)
    min_qty: 2
    add_ons: [{id: photo, name: Photo package, unit: flat, price: "50.00"}]
    rules:
      - {rule: group_discount, tiers: [{min_qty: 10, percent: "10"}, {min_qty: 20, percent: "15"}]}
      - {rule: customer_surcharge, customer_type: corporate, percent: "20"}   # or fixed: "75.00" (exactly one)
```
Rules are a discriminated union on `rule` (`GroupDiscount | CustomerSurcharge`), same style as `Qualification.Rule`. Validators: unique service/add-on ids, tiers strictly increasing in `min_qty`, currency `^[A-Z]{3}$`, `customer_type` in `{consumer, corporate}` (a closed set so input validation and pack agree), at most one rule of each type per service. `capacity.yaml`, `connectors.yaml`, `reviews:`, `intake:` shapes are in sections 4-7.

Cross-file validation in `load_pack` (raise `PackError` with file + field): none required between optional files, except `connectors.brief.send_hour` in `0..23` (model-level) and capacity shift windows `start < end` same day (model-level). Keep it that simple.

### 2. Migration 007 design (answers Q2)

One file `db/migrations/007_engine_modules.sql`, idempotent (`IF NOT EXISTS`, `DROP POLICY IF EXISTS`), same shape as 005. No `tenant_id` DEFAULT (005 dropped defaults; new tables never get one). Use `serial`/`bigserial` ids so `pg_get_serial_sequence` grants work. `bootstrap._run` escapes `%` as `%%`, so `format('%I')` in DO blocks is safe (Phase 6 deviation 1).

```sql
CREATE TABLE IF NOT EXISTS drafts (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  kind text NOT NULL CHECK (kind IN ('quote','review_reply')),
  status text NOT NULL CHECK (status IN ('pending','approved','rejected','needs_human','sent')),
  payload jsonb NOT NULL DEFAULT '{}',
  input_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS drafts_open_dedupe ON drafts (tenant_id, kind, input_hash)
  WHERE status IN ('pending','needs_human');           -- same request twice => same open draft
CREATE INDEX IF NOT EXISTS drafts_tenant_status_idx ON drafts (tenant_id, status, id);

CREATE TABLE IF NOT EXISTS capacity_flags (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  flag_key text NOT NULL,                  -- "{kind}:{shift_id}:{local_date}"
  kind text NOT NULL CHECK (kind IN ('over_capacity','understaffed','under_utilised')),
  shift_id text NOT NULL, shift_date date NOT NULL,   -- tenant-local date
  input_hash text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}',
  first_flagged_at timestamptz NOT NULL DEFAULT now(),
  reflagged_at timestamptz, resolved_at timestamptz,
  UNIQUE (tenant_id, flag_key)
);
CREATE TABLE IF NOT EXISTS brief_runs (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  run_date date NOT NULL,                  -- tenant-local date
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_date)
);
CREATE TABLE IF NOT EXISTS intake_people (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  person_key text NOT NULL, name text,
  waiver_at timestamptz, checkin_at timestamptz,
  result jsonb, result_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, person_key)
);
```
Then, in one `DO $$` block over the four names (mirror 005): `GRANT SELECT, INSERT, UPDATE ON <t> TO app_rw` (no DELETE: retention/`delete_subject` in Phase 9 run in the system context; if the planner prefers, grant DELETE on `intake_people` only), `GRANT USAGE, SELECT ON SEQUENCE <pg_get_serial_sequence(t,'id')> TO app_rw` (sequence grants are mandatory; "no default privileges" is Phase 6 policy), `ENABLE` + `FORCE ROW LEVEL SECURITY`, `DROP POLICY IF EXISTS tenant_isolation` + `CREATE POLICY tenant_isolation ... USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`. The `app_rw` role already exists (005), so this file does not recreate it. `drafts.tenant_id` index not needed beyond the composite ones.

**Applied-migration trap.** `apply_migrations` skips any version already in `schema_migrations` and has no checksum (`shortcut:` comment in bootstrap.py [VERIFIED]). Finalise 007 in Plan 02 before any run on the dev volume; fix-ups after that are `008_*.sql`. The `./db:/srv/db:ro` mount means new files are visible in the container immediately, but the API must restart (lifespan `bootstrap_schema`) or tests must call `apply_migrations()` to apply them. Add to `conftest.py` a session-scoped autouse fixture calling `bootstrap.apply_migrations()` (idempotent, owner engine) so `make g-test` never fails on missing tables.

**`assert_rls_enforced` extension** (`db.py`): keep the existing role/owner check, add a coverage check and an optional `eng` parameter (default `app_engine`, so `main.py` call is unchanged):
```python
rows = c.execute(text(
  "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
  "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id' AND NOT a.attisdropped "
  "WHERE n.nspname='public' AND c.relkind='r' AND has_table_privilege(current_user, c.oid, 'SELECT') "
  "AND NOT (c.relrowsecurity AND c.relforcerowsecurity)")).scalars().all()
if rows: raise RuntimeError(f"RLS missing on tables granted to app role: {sorted(rows)}")
```
The privilege filter excludes `tenant_api_keys` (has `tenant_id`, ungranted by design) [VERIFIED: 006 + test_rls_proof]. Unit test: on the `rls` scratch fixture, create `bad_t(tenant_id uuid)` + `GRANT SELECT ... TO app_rw`, call `assert_rls_enforced(role_eng)`, expect `RuntimeError` naming `bad_t`; control: unmodified scratch DB passes.

**Test-suite extensions (exact edits).**
- `test_rls_proof.py`: append the 4 tables to `TABLES` (keep `HAD_DEFAULT = TABLES[:9]` correct: it slices the first 9, unaffected by appends) and add `INSERTS` entries (valid minimal columns, e.g. `"drafts": "INSERT INTO drafts (tenant_id, kind, status, input_hash) VALUES (:t,'quote','pending','h')"`, `capacity_flags` with `flag_key,kind,shift_id,shift_date,input_hash`, `brief_runs` with `run_date`, `intake_people` with `person_key`). The catalog test (`tabs - {"tenant_api_keys"} == set(TABLES)`) then passes only if 007 enables RLS everywhere. Add the four to `SELF_CONTAINED` (no-context insert rejected). `test_superuser_control_sees_all` expects 2 rows per table: the fixture inserts one per tenant, satisfied.
- `test_leak.py`: `test_app_role_without_context_sees_zero_rows` parametrizes a hard-coded `TABLES`; replace the parametrize with a catalog-derived loop (tables with `tenant_id` where `has_table_privilege('app_rw',...,'SELECT')`) so later table additions cannot be forgotten. Add HTTP leak tests per module route family (tenant A cannot see B's draft/flag/brief/person; approve of B's draft id by A -> 404).
- `conftest.py` cleanup: add `drafts, capacity_flags, brief_runs, intake_people` to the `for t in (... )` DELETE loop *before* `DELETE FROM tenants` (FK; Phase 6 plan 04 saw a teardown FK error from `faq_chunks` ordering [VERIFIED: 06-04-SUMMARY "Not verified"], so keep the new deletes inside the same loop that precedes the tenants delete). Test tenants must use slug `test-*`.
- `test_migrations.py`: add `007_engine_modules` to the applied-and-idempotent assertion (pattern of `test_005_006_applied_idempotent...`).

### 3. Quote builder (answers Q3)

**Types** (`engine/quote.py`, frozen dataclasses):
```python
@dataclass(frozen=True) class QuoteRequest: service_id: str|None; qty: int|None; add_on_ids: tuple[str,...]=(); customer_type: str|None=None
@dataclass(frozen=True) class Line: kind: Literal["service","add_on","discount","surcharge"]; ref: str; label: str; qty: int; unit_price: Decimal|None; amount: Decimal
@dataclass(frozen=True) class Quote: currency: str; lines: tuple[Line,...]; total: Decimal
@dataclass(frozen=True) class NeedsHuman: reason: Literal["missing_input","unknown_service","unknown_add_on","missing_price","qty_below_min","qty_not_applicable","rule_unevaluable"]; missing: tuple[str,...]
```
`build_quote(pack, req) -> Quote | NeedsHuman`. The API-level DTO is a pydantic model (`extra="forbid"`, `qty` int 1..10_000, `add_on_ids` max 20, `customer_type` literal) so malformed JSON is 422; *absent* fields reach the builder as `None` and produce `NeedsHuman("missing_input", missing=[...])` (this is the "ask" path).

**Rules (pin these; all arithmetic in `Decimal`, `ROUND_HALF_UP`, exponent from a constant `CURRENCY_EXP = Decimal("0.01")`; zero-decimal currencies like JPY unsupported, state in a `shortcut:` comment):**
1. Service line amount = `price * qty` (`per_person`, `per_hour`: qty = people/hours); `flat`: qty must be 1 (else `NeedsHuman("qty_not_applicable")`), amount = price.
2. `min_qty` check before pricing (`qty_below_min`).
3. Add-ons: `per_person` scales with the service qty, `flat` once; any add-on with `price is None` -> `missing_price`; unknown id -> `unknown_add_on`.
4. `group_discount`: highest tier whose `min_qty <= qty`; applies to the service line only (not add-ons); emitted as a negative `discount` line `-(service_amount * pct / 100)` quantized at line creation.
5. `customer_surcharge`: applies when `customer_type` matches; base = service line + add-ons + discount line (i.e. the discounted subtotal); `percent` -> `base * pct/100` quantized, or `fixed` amount; positive `surcharge` line.
6. **Rounding interpretation (flag for confirmation):** D-04 says "total quantized once at the end". Because the email must quote line amounts and they must add up, quantize each derived line (percent lines) at creation with `ROUND_HALF_UP` and set `total = sum(line.amount)` (already 2-decimal, so no further rounding). Invariant `total == sum(lines)` is asserted in tests. This satisfies the intent (no float drift, no re-rounding of a total) while keeping displayed lines consistent.
7. Any service with `price is None` -> `NeedsHuman("missing_price", missing=("price",))`; a rule whose precondition input is absent (e.g. `customer_type` is None while the service has a surcharge rule) -> `NeedsHuman("rule_unevaluable", missing=("customer_type",))`.

Output money everywhere as strings (`format(d, "f")`). FastAPI's `jsonable_encoder` turns `Decimal` into `float`/`int` (e.g. `35.00` -> `35.0`) [ASSUMED: FastAPI encoder table; verify with a one-line test], so route response models use `str` fields. The `drafts.payload` jsonb stores amounts as strings; `json.dumps(..., default=str)` is a smell: build the dict explicitly.

**LLM paths** (call `llm.chat(...)` via module attribute `from .. import llm`, then `llm.chat(...)`, so `monkeypatch.setattr(llm, "chat", fake)` works exactly as in `test_agent.py` [VERIFIED: test_agent.py lines 36/75/108]; `from ..llm import chat` would bypass the fake):
- Optional extraction: `quote-extract.v1.md` prompt returns JSON `{service_id, qty, add_on_ids, customer_type}`; parse with pydantic; discard any value that fails validation or whose digits are not in the email (grounding, same spirit as `policy.is_grounded`); ungrounded/missing fields stay `None` -> `NeedsHuman(missing_input)`. Unknown service ids are rejected by the builder.
- Email: `quote-email.v1.md` (`load_prompt` expects first line `version: x` [VERIFIED: llm.load_prompt]). The prompt receives code-formatted figures (service name, qty, each line label + formatted amount, total with currency) and is told to use only those. Never pass raw prices from the model's memory.
- `llm.chat` raising `RuntimeError` (all providers down) -> route returns 502 and creates no draft (so a retry is not blocked by the open-draft unique index).

**Text validation** (`engine/quote_text.py`, pure): `check_quote_text(text, quote, pack_percents) -> list[str]` of codes.
- Amount tokens to extract: a number adjacent to a currency marker (`CHF|USD|EUR|GBP|Fr\.|[$€£]` before or after, or the words francs/dollars/euros), a number followed by `per person|/person|per hour|each|pp`, and any bare number with exactly two decimals (`\d[\d'., ]*[.,]\d{2}`).
- Normalise: the last separator followed by 1-2 digits is the decimal mark; a separator followed by exactly 3 digits is a group separator (`'`, `,`, `.`, space, U+202F); then compare as `Decimal` (so `1750` == `1750.00`). Test matrix: `1'750.00`, `1,750.00`, `1.750,00`, `1750`, `CHF1750`, `1 750.00`.
- Pass iff: every extracted amount is in `{total} U {line amounts} U {absolute line amounts} U {unit prices}`; total appears at least once; no foreign currency code (different from pack currency); any `%` figure equals an applied rule percent. Plain integers without currency context (party size, dates, times) are NOT checked. This is the documented interpretation of D-07 "every number ... no other currency amounts": checking every integer would reject any email mentioning a date.
- Flow: attempt 1 -> check; on failure regenerate once with the violation codes appended (codes only); fail again -> draft `needs_human` with `payload.quote` kept, `email_text` null, `check_failures` codes. A valid quote with failed text is still useful to the human.
- `NeedsHuman` quote -> draft `needs_human` with `payload.needs_human = {reason, missing}`, no LLM call.

**Draft + routes.** `POST /quotes` (`require_tenant`, `require_module(pack, "services")`), body `{request?: {...}, email_text?: str (max 4000), customer_name?: str}` (at least one of `request`/`email_text`). `input_hash = sha256(canonical_json({"v":1,"pack":pack.hash,"request":<validated request or email_text>}))`. Create via `INSERT ... ON CONFLICT (tenant_id, kind, input_hash) WHERE status IN ('pending','needs_human') DO NOTHING RETURNING id`; if no row returned `SELECT` the existing open draft and return it with `deduped: true`. Approve/reject in `drafts.py` (shared with review drafts): `UPDATE drafts SET status=:s, decided_at=now() WHERE id=:i AND tenant_id=:t AND status='pending' RETURNING id` (rowcount 0 -> 404 if absent, 409 if not pending; only `pending` can be approved, `needs_human` can only be rejected/dismissed). `sent` exists in the CHECK for Phase 8 (n8n marks sent); no endpoint in Phase 7. Record `record_event(c, tenant, None, "draft_created"|"draft_decided", {"draft_id": id, "kind": kind, "status": s})` (ids only; `conversation_id` is nullable [VERIFIED: 004]).

**Rate limiting:** the two LLM-calling routes (`POST /quotes` with `email_text`, `POST /reviews/draft`) are keyed by tenant and can burn provider quota. Reuse `ratelimit.allow(key=tenant_id, limit=...)` with a new constant in `config.py` (e.g. `module_llm_rate_per_min: int = 30`). Cheap and consistent with the "rate limits on public endpoints" rule.

### 4. Capacity checker (answers Q4)

`capacity.yaml`:
```yaml
shifts:
  - {id: weekday_evening, name: Weekday evening, days: [mon, tue, wed, thu, fri], start: "17:00", end: "23:00", min_staff: 2, max_covers_per_staff: 10, staff: 3}
  - {id: weekend_day, days: [sat, sun], start: "10:00", end: "18:00", min_staff: 3, max_covers_per_staff: 8, staff: 4, max_covers: 30}
  - {id: sunday_night, days: [sun], start: "00:00", end: "06:00", min_staff: 1, max_covers_per_staff: 10, staff: 1}
horizon_days: 14
```
Day tokens `mon..sun` are strings (YAML 1.1 turns `on/off/yes/no/y/n` into bools, none collide; still validate the set). `start < end` same-day (overnight shifts across midnight unsupported: `shortcut:` comment, split into two shifts). Rota = per-shift default `staff`; the request may carry `staff_overrides: [{shift_id, date, staff}]` for the actual rota (a future sheet connector can feed it). `max_covers` optional hard resource cap: `capacity = min(staff*max_covers_per_staff, max_covers)`.

**Pure API** (`engine/capacity.py`): `check_capacity(cap: Capacity, tz: ZoneInfo, bookings: Sequence[Booking(start: aware dt, covers: int)], first: date, last: date, overrides) -> list[Flag]`. The tz is an explicit argument (so DST tests can use Denver while the fixture pack is Zurich); the route passes `ZoneInfo(pack.meta.timezone)`.

**Window math (DST-safe).** For each local date `d` in range whose weekday is in `shift.days`: `start_utc = datetime.combine(d, shift.start, tzinfo=tz).astimezone(UTC)`; `end_utc` likewise from `shift.end`; a booking belongs to the shift iff `start_utc <= booking.start < end_utc` (compare instants in UTC, never `start + timedelta(hours=n)` on aware local datetimes). Verified this session with zoneinfo on 3.x [VERIFIED: local run]:

| Case | Shift 00:00-06:00 local | UTC window | Real length |
|------|------------------------|-----------|-------------|
| America/Denver spring-forward Sun 2026-03-08 | 2026-03-08T07:00Z -> 12:00Z | | 5h |
| America/Denver fall-back Sun 2026-11-01 | 2026-11-01T06:00Z -> 13:00Z | | 7h |
| Europe/Zurich spring-forward Sun 2026-03-29 | 2026-03-28T23:00Z -> 2026-03-29T04:00Z | | 5h |
| Europe/Zurich fall-back Sun 2026-10-25 | 2026-10-24T22:00Z -> 2026-10-25T05:00Z | | 7h |

Additional verified instants: Zurich nonexistent 02:30 on 2026-03-29 with fold=0 maps to 01:30Z (=03:30 CEST); Denver ambiguous 01:30 on 2026-11-01 is 07:30Z (fold=0, MDT) or 08:30Z (fold=1, MST); the Denver transition instants are 2026-03-08T09:00Z and 2026-11-01T08:00Z; both Zurich transitions are at 01:00Z. Required test cases: (a) the four windows above have the stated lengths; (b) fall-back day: bookings at 07:30Z and 08:30Z both fall inside the 00:00-06:00 shift and are counted as two separate bookings (do not dedupe by local wall time); (c) spring-forward: a booking at 2026-03-08T06:59Z (23:59 MST Mar 7) belongs to Mar 7, one at 09:30Z (03:30 MDT) to Mar 8; (d) shift `01:00-04:00` in Zurich on 2026-03-29 spans 2 real hours; (e) a shift starting in the gap (`02:30`) resolves with fold=0 and is documented/tested; (f) bookings near midnight UTC but different local dates land on the local date; (g) `flag_key` is built from the local date, so fall-back day yields one key, not two.

**Flag logic** (per shift occurrence; `staff` from override else default; `covers = sum(booking.covers)`; `cap = min(staff*per_staff, max_covers or inf)`; integer math only):
- `over_capacity`: `covers > cap`.
- `understaffed`: `staff < min_staff and covers > 0`.
- `under_utilised`: `staff > max(min_staff, ceil(covers / per_staff))` (a person more than the bookings need; `ceil` via `-(-covers // per_staff)`).
Each kind is its own flag; one shift can produce several. No fuzzy thresholds, so evals are exact.

**Stable keys and hashes.** `flag_key = f"{kind}:{shift.id}:{local_date.isoformat()}"`. `input_hash = sha256(canonical_json({staff, min_staff, per_staff, max_covers, covers, bookings: sorted [(start_utc_iso, covers)]}))`; covers-only would miss a moved booking. Hash is of the *inputs that justify the flag*, so a booking that changes covers 25->31 re-flags, while rerunning identical data does not.

**Classification (pure, so evals can test it)** `classify(existing: dict[flag_key, (input_hash, resolved_at_is_null)], computed: list[Flag], checked_dates: range) -> {new, unchanged, reflagged, resolved}`:
- computed key absent in DB -> `new` (INSERT);
- present, unresolved, same hash -> `unchanged` (no write);
- present, hash differs, or previously resolved -> `reflagged`: UPDATE `input_hash, details, reflagged_at=now(), resolved_at=NULL`;
- unresolved DB flag with `shift_date` inside the checked range but not computed now -> `resolved` (UPDATE `resolved_at=now()`; row kept for history, never deleted).
Only flags within the checked date range may be resolved (a run for next week must not resolve flags for next month). Persist via `INSERT ... ON CONFLICT (tenant_id, flag_key) DO NOTHING RETURNING id`; if nothing returned, `SELECT ... FOR UPDATE` and compare (race-safe, no CASE-in-upsert gymnastics). Response: `{checked_shifts, flags:[{flag_key, kind, shift_id, date, staff, covers, capacity, status}], resolved:[keys]}`; Phase 8's alert uses `status in (new, reflagged)` only, so repeated checks do not re-alert. `GET /capacity/flags?open=true` lists unresolved.

**Bookings data source (recommendation):** request body `bookings: [{start (ISO with offset), covers}]` (validated: aware datetime required, covers 1..1000) or, when omitted, the `bookings` connector if enabled in `connectors.yaml` (wired in Plan 05; Plan 04 supports body only). Do **not** build the `appointments`-table source: `appointments` links a lead to a slot with no party size (covers would always be 1), and no capacity-enabled pack uses slots. Record the omission as a `shortcut:` comment. Naive datetimes -> 422 (a naive time would be silently interpreted in server tz).

### 5. Connectors, brief, `due` (answers Q5)

```python
@dataclass(frozen=True)
class ConnectorResult:
    name: str                       # "bookings" | "sheet" | "accounting" | "ads"
    source: str = "mock"            # D-11: every result carries source="mock"
    ok: bool = True
    metrics: Mapping[str, Decimal] = field(default_factory=dict)
    error: str | None = None        # set when ok=False

class Connector(Protocol):
    name: str
    def fetch(self, tenant: TenantRef, day: date) -> ConnectorResult: ...
```
`TenantRef(slug: str, tenant_id: str)` frozen dataclass. Registry `dict[str, Callable[[SourceCfg], Connector]]` keyed by `name`. Seed: `random.Random(f"{slug}:{name}:{day.isoformat()}")` (or `int(sha256(...).hexdigest(), 16)` to remove any doubt) so output is identical across runs and processes. Metric catalog (fixed ordering in code): `bookings` -> `bookings_count`, `covers`; `sheet` -> `bookings_count`, `walk_ins`; `accounting` -> `revenue`, `outstanding_invoices` (Decimal, 2 dp); `ads` -> `ad_spend`, `ad_leads`.

`connectors.yaml` (explicit, so the fixture can exercise every path without monkeypatching adapters):
```yaml
sources:
  - {name: bookings}
  - {name: sheet, mock: {offsets: {bookings_count: 3}}}   # deterministic disagreement
  - {name: accounting}
  - {name: ads, mock: {unavailable: true}}                  # deterministic failure
brief: {send_hour: 7, tolerance: {bookings_count: {abs: 1, pct: 0}}}
```
`mock.offsets` and `mock.unavailable` are the only mock knobs; `kind` defaults to `mock` (the real-adapter value is a v2 extension; unknown kinds fail validation). Adapter exceptions are caught by the brief builder and become `ConnectorResult(ok=False, error=type(e).__name__)`; the brief renders "ads: source unavailable". It must never omit a configured source and never print `str(e)` (may contain internals).

**Disagreement:** group metrics by name across ok sources; for any metric reported by >= 2 sources, flag if `abs(a-b) > max(tol.abs, max(a,b)*tol.pct/100)` (default tolerance 0). Output both numbers and source names: `bookings_count: bookings=14 vs sheet=17 (diff 3, tolerance 1)`. Disagreement only compares sources that are ok; an unavailable source is reported as such, never as a disagreement.

**Brief** (`engine/brief.py`, pure): `build_brief(pack, results, local_date) -> Brief(sections, disagreements, text)`. Reports the tenant-local *previous day* (closed day, stable numbers); header uses `pack.meta.business`, the local date and tz name. Text is templated lines (one page): a header, `(mock data)` appended to every section whose result has `source == "mock"` (all of them in Phase 7), then the disagreement block, then unavailable lines. `html = "<pre>" + html.escape(text) + "</pre>"` is sufficient (email-safe, no template engine). Money formatted from `Decimal` with the pack currency; no LLM.

**Routes.** `POST /daily-brief` (`require_tenant`): compute local date from `pack.meta.timezone`; if a `brief_runs` row exists for `(tenant, local_date)` return its stored payload (idempotent for n8n retries), else compute, `INSERT ... ON CONFLICT (tenant_id, run_date) DO NOTHING`, return. Body `{force: bool=false}` recomputes and overwrites (a failed connector would otherwise be pinned for the day). Time is injected through one module function `utcnow()` in `brief_routes.py` that tests patch.

**`POST /daily-brief/due` semantics (resolves an ambiguity in D-12 / ROADMAP Phase 8 SC3).** Auth: `Depends(require_scope)` (exists in `auth.py`): a tenant key gets `{"due": [self-or-empty]}`; the admin key without `X-Tenant-Id` iterates all tenants (read from `tenants` in `system()`, as `get_pack` does) and reads each tenant's `brief_runs` through its own `tx(tid)` so RLS still applies; admin with `X-Tenant-Id` behaves like a tenant. Tenants without `connectors.yaml` are skipped. Per tenant: `local = now_utc.astimezone(ZoneInfo(pack.meta.timezone))`; due iff `local.hour >= send_hour` and `local.hour < send_hour + BRIEF_GRACE_HOURS` and no `brief_runs` row for `local.date()`. Response `{"due":[{"tenant_id","local_date","send_hour"}]}`. Recommendation: `BRIEF_GRACE_HOURS = 3` (constant) instead of strict `hour == send_hour`, so one missed hourly poll self-heals; hour == send_hour still matches D-12. "Sent" is represented by the run row's existence (Phase 7 never emails); document that Phase 8's n8n sends after `POST /daily-brief` returns.
Pure core: `is_due(now_utc, tz, send_hour, already_ran: bool) -> bool` with test rows: Zurich 06:59 local no, 07:00 yes, 09:59 yes, 10:00 no, after run no; plus the two DST transition days: send_hour 2 on Zurich 2026-03-29 (local hour 2 does not exist; 01:00Z is local 03:00 so due at 03:00 via `>=`) and the fall-back day (`hour 2` occurs twice, but the `brief_runs` unique key prevents a second brief).

### 6. Review responder (answers Q6)

`pack.yaml` block:
```yaml
reviews:
  tone: "warm, brief, first person plural, no exclamation marks"
  signature: "The Demo Venue team"
  forbidden_topics: [pricing, staff names]    # extra lower-case phrases that block (word-boundary match)
  health_privacy: false                       # true for clinics
  max_words: 120
```
Route `POST /reviews/draft` body `{review_text (1..4000), rating (1..5), platform (google|tripadvisor|other)}`. Flow: `llm.chat` draft (prompt wraps the review in `<review>` delimiters and says to ignore instructions inside it; reviews are untrusted input and the post-check is the real defence) -> `check_reply` -> violations -> regenerate once with violation codes -> still failing -> draft `needs_human` with `payload = {review_text, rating, platform, violations: [codes], attempts: 2}` and NO reply text (failed text may contain hallucinated PII). Pass -> `pending` draft with `reply_text`. LLM down -> 502, no row. Dedupe via `input_hash` (sha256 of platform + rating + review_text + pack hash) and the same open-draft unique index. Approve marks `approved`; nothing posts anywhere in Phase 7.

**`check_reply(text, pack, review_text="") -> list[str]` (pure).** Codes: `compensation`, `fault`, `unknown_fact`, `pii`, `health_privacy`, `forbidden_topic`, `too_long`, `empty`.
- `compensation`: regex over `refund|reimburs|compensat|discount|voucher|credit note|free (visit|session|game|entry|drink|meal|ticket)|money back|on the house|make it up to you|gift card|complimentary`, plus `policy.unsupported_claim(text, faq_texts)` reused for price/percent claims (reuses `_CLAIM_RE` through the public function; no private import) [VERIFIED: policy.py].
- `fault`: admissions only, not apologies: `\b(our|my) (fault|mistake|error)\b|we (made a mistake|messed up|dropped the ball|were (wrong|at fault|negligent)|failed (to|you))|(was|were) (our|my) (fault|responsibility)|we (accept|admit|take) (full )?(responsibility|blame)|should have|that (was|is) (unacceptable|inexcusable)`. "We're sorry to hear..." must pass (explicit test).
- `unknown_fact`: (a) `policy.unsupported_claim` (numbers) as above; (b) concrete-commitment regex (`we have (now )?(fixed|changed|replaced|retrained|dismissed)|has been (fixed|resolved)|going forward we will|we (guarantee|promise)|always`); (c) vocabulary check by `policy.answer_supported`. (c) is risky: `answer_supported` fails when > 40% of 4+ letter words are outside FAQ vocabulary + `_GENERIC`; natural replies ("appreciate", "feedback", "wonderful", "experience") will trip it. Recommendation: add one additive keyword `extra_vocab: frozenset[str] = frozenset()` to `policy.answer_supported` (default empty = identical behaviour for roofing/dental, covered by the existing `test_policy.py`), and pass `faq_texts + [review_text, reviews.tone, pack.meta.offer, pack.meta.kind]` tokens plus a constant `REVIEW_GENERIC` word set defined in `engine/reviews.py`. Calibrate against fixture drafts (good replies must pass, fabricated-fact replies must fail); tune the word list, do not loosen the threshold. This is the single heuristic most likely to need iteration; allow time in Plan 06.
- `pii`: patterns from `engine/pii.py` (`EMAIL_RE`, `PHONE_RE = \+?\d[\d\s().-]{7,}\d`, `ADDRESS_RE` = number + capitalised word + street suffix (Street|St|Strasse|Str\.|Ave|Road|Rd|Weg|Platz|Lane|Blvd)); strip allow-listed business contact strings first (pack `owner_email`, emails/phones occurring in FAQ text) so a signature with the business phone is not blocked. Phase 9's `mask()` will import the same patterns (avoid two diverging regex sets).
- `health_privacy` (only when `reviews.health_privacy: true`): block confirming a customer relationship or treatment: `\byour (visit|appointment|treatment|procedure|filling|cleaning|check-?up|teeth|tooth|gums|x-?rays?|records?|chart|dentist|doctor)\b|\bas (our|a) patient\b|\bwhen you (came|visited)\b|\bwe (treated|saw|examined) you\b|\byou (were|are) (a|our) patient\b`. A compliant reply is generic ("Thank you for your feedback. We can't discuss individual cases publicly, please contact us directly"). The dental pack gets no `reviews:` block in Phase 7 (D-01), so this rule is exercised through the fixture pack with the flag overridden (`pack.model_copy(update=...)` works on frozen pydantic models) and via eval cases carrying `health_privacy: true`.
- `forbidden_topic`: pack-listed phrases (`re.escape`, word boundaries, case-insensitive); `too_long`: word count > `max_words`.

**No sentiment gating (all ratings, same path):** only the prompt text includes the rating; no code branch reads `rating`. Test: run ratings 1..5 through the same fake LLM and assert identical status/violations; add a grep-style test asserting the module's functions never compare `rating` (or simply review). Google's policy context: gating means selectively soliciting reviews from happy customers and discouraging negative ones, and requires review requests to go to all customers equally; secondary sources agree, but Google's own policy page was not located this session, so verify wording before quoting in customer-facing docs [CITED: https://www.podium.com/online-reviews/review-gating/, https://seologist.com/knowledge-sharing/what-is-review-gating-and-why-does-it-violate-googles-review-policies/ -- secondary sources, MEDIUM-LOW]. This applies to review *requests* (Phase 8 `post-visit review request`, not in Phase 7), so Phase 7's obligation is: replies treat every rating identically and are never auto-posted. A reply API exists (`PUT .../reviews/*/reply` in Business Profile API v4, only valid for verified locations) [CITED: https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/updateReply]; Phase 7 must not call it. Also never edit or hide replies to negative reviews differently from positive ones.

### 7. `intake_event` (answers Q7)

`pack.yaml`:
```yaml
intake:
  waiver:  {person_key: [guest.email, guest.phone], name: guest.name, occurred_at: signed_at}
  checkin: {person_key: [guest.email, guest.phone], name: guest.name, occurred_at: arrived_at}
  result:  {person_key: [guest.email], name: guest.name, occurred_at: finished_at, fields: {score: game.score, team: team.name, time_seconds: game.time}}
```
Model `Intake(waiver|checkin|result: EventMap | None)` with at least one set; `EventMap(person_key: tuple[Path,...] (1..3), name: Path|None, occurred_at: Path|None, fields: dict[str, Path] = {})`, `fields` only valid on `result`. `Path` = string matching `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$` (no list indexes, no JSONPath: `shortcut:` comment). Mapping YAML values are plain strings so no YAML-1.1 coercion risk.

Request: `POST /intake_event` body `{event: "waiver"|"checkin"|"result", payload: {...}}`, `require_tenant`, `require_module(pack.meta.intake)`; unknown event type or one the pack did not map -> 422. Payload size guard: `len(json.dumps(payload)) <= 32_768`, depth/keys naturally bounded.

`engine/intake.py` (pure): `get_path(obj, path)` returns a `MISSING` sentinel when a segment is absent or an intermediate is not a dict; `normalise_event(map, event, payload) -> NormalisedEvent | list[FieldError]`:
- `person_key`: first non-empty of the mapped paths; value must be `str|int` (reject dict/list/bool), stripped, <= 200 chars; emails lowercased; phone-like values reduced to `+` and digits; else kept lowercased. Normalisation is what makes a waiver (email) and check-in (same email, different case) the same person. A person identified by phone in one event and email in another stays two rows (documented limit; resolution is a v2 identity-merge problem).
- `name` <= 200 chars, optional; `occurred_at` parsed as aware ISO datetime, else `now()` (replays stay idempotent because of `LEAST` below); `result` fields must be scalars (str/int/float/bool/None), <= 20 fields, strings <= 500.
- Errors name the *mapping* path and event, never echo the value: `422 {"detail":[{"event":"waiver","field":"person_key","tried":["guest.email","guest.phone"],"msg":"missing"}]}`.

**Idempotent upsert (one statement per event, `db.tx(tenant)`):**
```sql
INSERT INTO intake_people (tenant_id, person_key, name, waiver_at) VALUES (:t,:k,:n,:at)
ON CONFLICT (tenant_id, person_key) DO UPDATE SET
  name = COALESCE(intake_people.name, EXCLUDED.name),
  waiver_at = LEAST(intake_people.waiver_at, EXCLUDED.waiver_at),   -- LEAST ignores NULLs in PG
  updated_at = now()
RETURNING id, (xmax = 0) AS created
```
`checkin` is the same shape on `checkin_at`; `result` sets `result = CASE WHEN intake_people.result_at IS NULL OR EXCLUDED.result_at >= intake_people.result_at THEN EXCLUDED.result ELSE intake_people.result END` and the same for `result_at` (a replayed older result cannot regress a newer one; replaying the identical event is a no-op). `updated_at` bumps on replay; acceptable (not part of the person's data). Response `{person_id, created: bool}`. Log `tenant, event, person_id` only; `record_event(... "intake_event", {"event": e, "person_id": id})`. `person_key` and `name` are PII: flag for the Phase 9 data map, retention purge and `delete_subject` (note in the SUMMARY; no Phase 7 action).

### 8. Eval layout and pytest (answers Q8)

```
evals/modules/__init__.py           # makes `python -m evals.modules` unambiguous (evals/ itself has no __init__.py today: namespace package)
evals/modules/__main__.py           # argparse: --module quote|capacity|brief|reviews|intake (default all); exit 1 if any case fails
evals/modules/loader.py             # load_cases(module) strict: unknown keys fail like runner.load_scenarios._bad; unique ids
evals/modules/<module>/cases.yaml
```
Run: `docker compose exec api python -m evals.modules [--module quote]` (add `make g-eval-modules`). `run(module) -> list[CaseResult]` is a plain function shared with pytest. Pack source: `Path(app.__file__).parent / "tests_data" / "packs"` via `load_pack(slug, base=...)`. No LLM and no DB: every module's decision logic is pure, which is why classification (`classify`), merging (`apply_event`) and `is_due` are pure functions.

Case shapes (strict key sets):
- quote: `{id, pack, input: {service_id, qty, add_on_ids, customer_type}, expect: {total: "..", lines: [{ref, amount}], needs_human: {reason, missing}}}`; plus `{id, kind: text_check, input: {...}, text: "...", expect: ok|fail, codes: [...]}`. Cases: tiers boundary (qty 9/10/19/20), corporate percent and fixed, missing price, qty below min, unknown add-on, per_hour, rounding half-up (e.g. 10% of 33.35), `total == sum(lines)`; text: apostrophe-thousands, wrong total, extra amount, foreign currency, no total, percent not applied.
- capacity: `{id, tz, shifts|pack, bookings, overrides, range, expect: {flags: [{key, kind}]}}`, `{kind: sequence, runs: [...], expect: [{status per key}]}` for dedupe/re-flag/resolve using in-memory prior state; DST cases from section 4 (tz is a case field).
- brief: `{id, pack, now_utc, results?: (mock overrides), expect: {text_contains: [...], disagreements: [...], unavailable: [...], due: bool}}`.
- reviews: `{id, pack, health_privacy?, review_text, rating, draft, expect: pass|block, codes: [...]}`: >= 4 cases per code, including must-pass benign replies, apology-not-fault, business phone allow-list, and the same cases across ratings 1..5.
- intake: `{id, pack, events: [{event, payload}...], expect: {people: [{person_key, waiver_at?, checkin_at?, result?}], errors: [...]}}` including duplicate event, out-of-order result, case-different email, missing person key, wrong type.

Pytest: `api/app/test_module_evals.py` parametrizes over `loader.load_cases` ids (so a failing case id is visible) and one test per module asserting `failed == 0`. It runs in `make g-test` with no LLM. DB-backed behaviour (upsert idempotency, flag persistence, draft dedupe, approve guards, brief_runs, RLS leak) lives in the module's own test files, not in evals. Phase gate at the end of the plan 08: `make eval-gate` (roofing 94/96 vs `evals/baselines/v1-roofing.json`) and `make g-eval ARGS="--pack bright-smile-dental --gate"` (43/43 vs `evals/baselines/bright-smile-dental.json`), then `make g-test` full suite. These need the local LLM and were NOT run in this research.

### 9. Plan split and fixture pack (answers Q9)

Sequential, each <= ~10 files (YAML data files counted). Pack models land in the plan that needs them (so `pack.py` is edited per plan, sequentially: no merge conflicts).

| Plan | Scope | Files (count) |
|------|-------|---------------|
| 07-01 Pack mechanism + fixture core | `OPTIONAL_FILES`/`_parse_optional`, `load_pack(slug, base)`, `Money/Percent/HHMM` validators, `Pack` optional fields, `Reviews`/`Intake` not yet; core 6 fixture YAMLs; hash-pin test | `api/app/pack.py`, `api/app/engine/__init__.py`, `api/app/test_pack_modules.py`, `tests_data/packs/demo-venue/{pack,calendar,qualification,escalation,messages,faq}.yaml` (9) |
| 07-02 Migration 007 + drafts + RLS | `007_engine_modules.sql` (4 tables), `assert_rls_enforced` coverage + `eng` param, conftest cleanup + `apply_migrations` fixture, `drafts.py` (create/dedupe, list/get/approve/reject), include router, catalog-derived leak loop + HTTP leak, rls_proof + migrations tests | `db/migrations/007_engine_modules.sql`, `api/app/db.py`, `api/app/conftest.py`, `api/app/drafts.py`, `api/app/main.py`, `api/app/test_drafts.py`, `api/app/test_rls_proof.py`, `api/app/test_leak.py`, `api/app/test_migrations.py` (9) |
| 07-03 Quote builder | `Services` models, `services.yaml`, `engine/quote.py`, `engine/quote_text.py`, `quotes.py`, prompts (extract + email), tests | `api/app/pack.py`, `demo-venue/services.yaml`, `engine/quote.py`, `engine/quote_text.py`, `api/app/quotes.py`, `prompts/quote-extract.v1.md`, `prompts/quote-email.v1.md`, `api/app/main.py`, `api/app/test_quote.py`, `api/app/test_quotes_api.py` (10) |
| 07-04 Capacity checker | `Capacity` models, `capacity.yaml`, pure checker + `classify`, persistence + route | `api/app/pack.py`, `demo-venue/capacity.yaml`, `engine/capacity.py`, `api/app/capacity_routes.py`, `api/app/main.py`, `api/app/test_capacity.py`, `api/app/test_capacity_api.py` (7) |
| 07-05 Connectors + brief | `Connectors` models, `connectors.yaml`, Protocol + 4 mocks, brief, `/daily-brief` + `/due`, wire bookings connector as capacity default source | `api/app/pack.py`, `demo-venue/connectors.yaml`, `engine/connectors.py`, `engine/brief.py`, `api/app/brief_routes.py`, `api/app/capacity_routes.py`, `api/app/main.py`, `api/app/test_connectors.py`, `api/app/test_brief.py` (9) |
| 07-06 Review responder | `Reviews` block on `PackMeta`, fixture `pack.yaml` edit, `policy.answer_supported(extra_vocab=)`, `engine/pii.py`, `engine/reviews.py`, route, prompt | `api/app/pack.py`, `demo-venue/pack.yaml`, `api/app/policy.py`, `engine/pii.py`, `engine/reviews.py`, `api/app/reviews_routes.py`, `prompts/review-reply.v1.md`, `api/app/main.py`, `api/app/test_reviews.py` (9) |
| 07-07 intake_event | `Intake` block, fixture `pack.yaml` edit, `engine/intake.py`, route, DB tests | `api/app/pack.py`, `demo-venue/pack.yaml`, `engine/intake.py`, `api/app/intake_event_routes.py`, `api/app/main.py`, `api/app/test_intake_event.py` (6) |
| 07-08 Module evals + gates | `evals/modules` runner + 5 case sets, pytest wrapper, Makefile target, regression gates (roofing 94/96, dental 43/43), full pytest | `evals/modules/{__init__,__main__,loader}.py`, `evals/modules/{quote,capacity,brief,reviews,intake}/cases.yaml`, `api/app/test_module_evals.py`, `Makefile` (10) |

Order rationale: drafts infra before quote/review (both write drafts); capacity before connectors (bookings connector is wired in 05 by a one-line edit); intake is independent and last among modules; evals last so they test finished modules (each module plan still ships its own pytest tests, TDD per CLAUDE.md).

**Fixture pack `demo-venue` (synthetic, escape-room-style venue, Europe/Zurich):**
- `pack.yaml`: slug `demo-venue`, business "Demo Venue", kind "an escape room and event venue", offer "books escape rooms, team events and private parties", timezone `Europe/Zurich`, locale `en-CH`, plus (added in 06/07) `reviews:` and `intake:` blocks.
- `calendar.yaml`: Zurich, slot_hours [10,12,14,16,18], 60 min, 14 days, `weekdays_only: false`, buffer 0. `qualification.yaml`: one rule `service_type in_list [escape_room, private_event]` with matching `service_synonyms`, patterns copied from dental style (`owner_*: '(?!)'`), `extra_stopwords: [demo, venue]`. `escalation.yaml`: simple `safety` regex (e.g. injury/fire/ambulance), `always_human: [injury]`. `messages.yaml`: copy dental's keys with neutral text and `ask` keys exactly `service_type`, `name`, `"phone or email"`. `faq.yaml`: 3 entries (hours, location, groups). These six exist only because the loader requires them.
- `services.yaml` (CHF): `escape_room` per_person "35.00" min_qty 2, add_ons `photo` flat "50.00" and `drinks` per_person "8.50", rules `group_discount` tiers 10->"10", 20->"15" and corporate surcharge "20"%; `private_event` flat "600.00", corporate surcharge `fixed: "75.00"`; `team_building` per_hour "280.00" min_qty 2; `vip_experience` with no price (missing-price path).
- `capacity.yaml`: the three shifts in section 4 (weekday_evening, weekend_day with `max_covers: 30`, sunday_night 00:00-06:00 for DST days).
- `connectors.yaml`: as in section 5 (sheet offset +3 => disagreement, ads unavailable => explicit line, send_hour 7, bookings_count tolerance abs 1).
- `reviews`: tone, signature "The Demo Venue team", forbidden_topics [pricing], health_privacy false, max_words 120. `intake`: as in section 7.
Tests needing clean variants build them with `pack.model_copy(update={...})` (frozen models allow it) rather than extra fixture folders.

### 10. Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Money | float math, custom Money class | `Decimal` + `quantize(ROUND_HALF_UP)` + string I/O | Exactness; locked D-04 |
| Tenant-local scheduling | UTC offset arithmetic, pytz | `zoneinfo` + wall-time `combine(..., tzinfo=tz).astimezone(UTC)` | DST gaps/overlaps handled by fold |
| Idempotency/dedupe | read-then-write in Python | `UNIQUE` + `ON CONFLICT` (with partial-index predicate for drafts) | Race-safe |
| Tenant isolation | `WHERE tenant_id` only | `db.tx(tenant)` + FORCE RLS | Phase 6 pattern |
| Rule evaluation | json-logic/DSL | Pydantic discriminated union + dispatch dict | Locked in STACK.md |
| Request/DTO validation | manual dict checks | Pydantic `extra="forbid"` models | Boundary validation |
| PII regex | ad-hoc per module | one `engine/pii.py` (Phase 9 `mask()` reuses it) | Avoid diverging sets |
| Grounding/claim checks | new price regex | `policy.unsupported_claim` / `answer_supported` | Already tested |
| Audit | new log table | `db.record_event` -> `agent_events` | Append-only, RLS'd |

**Key insight:** every "decision" has a model on one side and a code check on the other; the model never writes a number or a state change that code does not recompute.

## Common Pitfalls

### Pitfall 1: YAML 1.1 coercions in pack files
**What goes wrong:** `price: 35.10` loads as float (precision), `start: 17:00` loads as int 1020, `no`/`on` become bools. **Why:** `yaml.safe_load` implements YAML 1.1. **Avoid:** `BeforeValidator`s that reject non-strings for money/time/percent with an instructive message; examples in fixture use quoted strings. **Warning sign:** a `PackError` like "money must be a quoted decimal string" is the intended behaviour; a pack that loads with a wrong price is the bug.

### Pitfall 2: Decimal leaving the engine as float
**What goes wrong:** FastAPI/`json.dumps` turn `Decimal("35.00")` into `35.0` or raise. **Avoid:** DTO fields and jsonb payload amounts are strings; one helper `fmt(d) = format(d, "f")`. Test: a quote total `"1234.50"` round-trips through HTTP and the DB unchanged.

### Pitfall 3: Editing an applied migration
**What goes wrong:** `apply_migrations` skips applied versions without checksum, so the dev DB keeps the old schema and tests fail only locally/CI-differently. **Avoid:** 007 final in Plan 02; later changes are 008+; `test_migrations` asserts the table set on a scratch DB (fresh) so CI catches drift between fresh and upgraded DBs.

### Pitfall 4: Forgetting RLS bookkeeping when a table is added
**What goes wrong:** new table without FORCE RLS/grant works for the owner/superuser engine and fails or leaks under `app_rw`. **Avoid:** the extended `assert_rls_enforced` (fails startup), the catalog-derived leak loop, the `test_rls_proof` TABLES/INSERTS entries, and sequence grants (missing `GRANT USAGE ON SEQUENCE` gives "permission denied for sequence" only at first INSERT).

### Pitfall 5: Faking the LLM at the wrong attribute
**What goes wrong:** `from ..llm import chat` binds early; `monkeypatch.setattr(llm, "chat", ...)` no longer applies and a test hits the network or the real chain. **Avoid:** `from .. import llm` and `llm.chat(...)`; in conftest-less tests use the `test_agent.py` pattern and `pytest.fail` fakes where the LLM must not be called (NeedsHuman path, check-only evals). Fake signature `lambda messages, providers=None` to be tolerant.

### Pitfall 6: DST via local timedelta arithmetic
**What goes wrong:** `local_start + timedelta(hours=6)` is wall-clock arithmetic for zoneinfo-aware values, giving a 6h window on a 5h/7h day. **Avoid:** build both ends from wall time and convert to UTC; compare instants; key by local date. Tests in section 4 pin the instants.

### Pitfall 7: Unconfigured capacity data silently "passing"
**What goes wrong:** no bookings supplied and no connector -> empty bookings -> everything `under_utilised`/resolved, wiping open flags. **Avoid:** if neither `bookings` in the body nor an enabled `bookings` connector exists, return 422 "no booking source"; an unavailable connector returns 503-style `source_unavailable` and the run must not resolve existing flags.

### Pitfall 8: Resolving flags outside the checked window
Only resolve flags whose `shift_date` is inside the run's date range (section 4).

### Pitfall 9: Review heuristic false positives drown the queue
`answer_supported` on natural reply language; mitigate with the `extra_vocab` keyword + fixture-driven calibration; every blocked reply goes to `needs_human`, so overly strict checks create manual work, overly loose ones are a safety issue. Keep safety checks (compensation, fault, PII, health_privacy) as strict regexes and treat `unknown_fact` as the tunable one.

### Pitfall 11: Prompt injection through review/email text
Untrusted text inside prompts. Delimit it, never let it select tools or fields, and rely on post-checks (quote text validated against the code-computed quote; replies against `check_reply`). Add one injection case to each of the reviews and quote-text eval sets.

### Pitfall 12: PII in logs and drafts
Intake `person_key`/`name`, review text and customer names must not enter `log.*` or `agent_events` payloads (ids only). `drafts.payload` and `intake_people` hold PII/customer text by necessity: record them in the Phase 9 data map and keep them tenant-scoped; no `exc_info` logging of request bodies.

### Pitfall 13: Module endpoints reachable with the admin key
Use `require_tenant` (tenant key only). `X-Admin-Key` alone must 401 on every module route except `/daily-brief/due` (via `require_scope`). Add to the route-scope tests.

### Pitfall 14: Mock labelled inconsistently
Add a test asserting every rendered brief section from a mock source contains `(mock data)` and every `ConnectorResult.source == "mock"`; the JSON response also carries `source: "mock"`.

### Pitfall 15: Pack cache and optional fields
`get_pack` caches by `(tenant, hash)`; adding optional fields does not break it. Tests that `model_copy` a pack must not write it back to the cache.

## Code Examples

### Optional file loading + base dir
```python
# Source: derived from api/app/pack.py (_parse, load_pack) [VERIFIED: read this session]
OPTIONAL_FILES = {"services": Services, "capacity": Capacity, "connectors": Connectors}

def load_pack(slug: str, base: Path | None = None) -> Pack:
    if not SLUG_RE.fullmatch(slug):
        raise PackError(f"invalid pack slug {slug!r}")
    root = (base or settings.businesses_dir) / slug
    parts = {n: _parse(root / f"{n}.yaml", m) for n, m in FILES.items()}
    opt = {n: (_parse(root / f"{n}.yaml", m) if (root / f"{n}.yaml").exists() else None) for n, m in OPTIONAL_FILES.items()}
    ...  # existing slug/ask checks unchanged
    return Pack(..., **opt)
```

### Tenant tx + open-draft dedupe insert
```python
# Pattern: db.tx (set_config transaction-local) + partial-unique ON CONFLICT
with tx(tenant) as c:
    row = c.execute(text(
        "INSERT INTO drafts (tenant_id, kind, status, payload, input_hash) "
        "VALUES (:t, :k, :s, CAST(:p AS jsonb), :h) "
        "ON CONFLICT (tenant_id, kind, input_hash) WHERE status IN ('pending','needs_human') DO NOTHING RETURNING id"),
        {"t": tenant, "k": kind, "s": status, "p": json.dumps(payload), "h": h}).first()
    if row is None:  # same request already open
        row = c.execute(text("SELECT id FROM drafts WHERE tenant_id=:t AND kind=:k AND input_hash=:h "
                             "AND status IN ('pending','needs_human')"), {"t": tenant, "k": kind, "h": h}).one()
```

### Capacity window (DST-safe)
```python
def window_utc(d: date, start: time, end: time, tz: ZoneInfo) -> tuple[datetime, datetime]:
    f = lambda t: datetime.combine(d, t, tzinfo=tz).astimezone(timezone.utc)
    return f(start), f(end)          # compare instants; never local_start + timedelta
```

### Guarded approve
```python
n = c.execute(text("UPDATE drafts SET status=:s, decided_at=now() "
                   "WHERE id=:i AND tenant_id=:t AND status='pending' RETURNING id"), ...).first()
# None: SELECT status to distinguish 404 (not visible/absent) from 409 (not pending)
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Roofing regex `_CLAIM_RE` for price claims | Per-pack quote text validation vs computed quote | Packs with `services.yaml` may state computed prices; roofing chat still refuses |
| Single global approval queue (untenanted `outreach`) | Tenant-scoped `drafts` with RLS | Outreach queue untouched |
| Fixed `engine.begin()` | `db.tx(tenant)` / `system()` | All module DB access via `tx` |

**Deprecated/outdated:** none relevant. `mcp` v2 and Anthropic provider are deferred (Phase 10).

## Runtime State Inventory
Not a rename/refactor phase: omitted by instruction. (Related note: after 007 lands, running dev/branch volumes need the API restarted or `apply_migrations()` once; the live roofdeskai.com DB is not touched, work stays on the `roofdesk-global` branch.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | pydantic-core's float->Decimal conversion path (avoided by rejecting floats) | 1 | None: mitigated by design |
| A2 | `yaml.safe_load("17:00")` -> int 1020 (YAML 1.1 sexagesimal); PyYAML not importable on the host python this session, so not re-run | 1, Pitfall 1 | If false the validator is merely unnecessary; keep a test either way |
| A3 | FastAPI `jsonable_encoder` encodes `Decimal` to float/int | 3, Pitfall 2 | Strings-only convention is harmless if wrong |
| A4 | `random.Random(str)` seeding is process-independent (CPython hashes str seeds with sha512, not `hash()`) | Stack | Mock data would differ per process; use sha256-derived int seed to remove doubt (recommended) |
| A5 | `Path.rglob` does not recurse symlinked dirs on 3.12 (copytree recommended regardless) | 1 | Hash differs between real and symlinked pack in tests |
| A6 | `python -m evals.modules` works with `evals/` as namespace package once `evals/modules/__init__.py` + `__main__.py` exist | 8 | Add `evals/__init__.py` if it errors |
| A7 | Quote rounding interpretation (quantize lines, total = sum) satisfies D-04 "quantized once" | 3 | If the user wants literal single-quantize, derived lines could mismatch the total by a cent |
| A8 | Review privacy regex list is sufficient for dental (needs fixture calibration; legal review before real patients) | 6 | Missed privacy language; Phase 9/legal |
| A9 | Google review-gating wording from secondary sources, official page not read | 6 | Documentation only |

## Open Questions

1. **Rounding semantics ("total quantized once")**
   - Known: D-04; email must quote line amounts.
   - Unclear: literal single quantization would break `total == sum(lines)`.
   - **Recommendation:** quantize derived lines at creation (`ROUND_HALF_UP`), total = sum of lines (no further rounding); record in the plan and SUMMARY. Resolve at plan time.
2. **`/daily-brief/due` caller and window**
   - Known: D-12 says "returns tenants"; tenant keys only see their own tenant under RLS; Phase 8 SC3 loops tenants.
   - **Recommendation:** `require_scope` (tenant key -> self, admin key -> all tenants via per-tenant `tx`), window `send_hour <= local_hour < send_hour + 3` (constant), "sent" = `brief_runs` row exists. Resolve in 07-05.
3. **Capacity bookings source**
   - **Recommendation:** request body or bookings connector; no `appointments` table source (no party size). Resolve in 07-04/05.
4. **`sent` draft status writer**
   - **Recommendation:** status stays in the CHECK; no Phase 7 endpoint; Phase 8 adds `POST /drafts/{id}/sent` when n8n sends.
5. **Reviews/intake block location**
   - **Recommendation:** optional fields on `PackMeta` in `pack.yaml` (matches D-01 "blocks"); not separate files.
6. **`answer_supported` additive keyword in `policy.py`**
   - Touches shared policy code used by the roofing agent (behaviour unchanged by default). **Recommendation:** do it, covered by `test_policy.py` plus the Phase 7 final 94/96 gate; fallback if the user dislikes touching `policy.py`: implement the vocabulary check locally in `engine/reviews.py` using `policy._tokens`.
7. **Pinned roofing/dental pack hashes in tests**
   - **Recommendation:** pin full sha256 values captured in Wave 0 (current prefixes above); a deliberate pack edit then needs a deliberate hash update.
8. **LLM-endpoint rate limit constant**
   - **Recommendation:** `module_llm_rate_per_min = 30` per tenant via `ratelimit.allow`.
9. **Confirm "call 144" Swiss emergency number** (carried in): still open, not a Phase 7 dependency.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 16 + pgvector (compose `db`) | RLS tests, migrations | not probed this session (read-only task); existing `make g-up` stack | existing | scratch DB fixture needs the cluster |
| Docker compose branch stack (`roofdesk-global`) | `make g-test`, `g-eval` | not probed | existing | — |
| Local Ollama / LLM chain | roofing + dental regression gates only | not probed | existing | Phase 7 module tests and evals use no LLM (fakes) |
| tzdata | Denver/Zurich tests | yes (`tzdata==2026.6` pinned); also resolved zoneinfo on the host this session | 2026.6 | — |
| PyYAML on host python | n/a (runs in container) | not importable on host | 6.* in container | run in container |

**Missing with no fallback:** none identified for module work. The 94/96 and 43/43 gates require the LLM stack and must be run by the executor at the end of Plan 08.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 582 passing at end of Phase 6 per 06-04-SUMMARY) |
| Config file | none beyond `api/app/conftest.py` (session cleanup + fixtures) |
| Quick run command | `make g-test ARGS="app/test_quote.py app/test_capacity.py -q"` (per-plan files) |
| Full suite command | `make g-test` |
| Module evals | `make g-eval-modules` (new) = `python -m evals.modules` inside the api container |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MOD-01 | Decimal totals, tiers, surcharge, NeedsHuman reasons | unit | `make g-test ARGS="app/test_quote.py -q"` | Wave: 07-03 |
| MOD-02 | draft created/deduped/approved; text vs quote check; regenerate once | unit+DB | `... app/test_quotes_api.py app/test_drafts.py` | 07-02/03 |
| MOD-03 | flags, dedupe, re-flag, resolve, DST windows (Denver, Zurich) | unit+DB | `... app/test_capacity.py app/test_capacity_api.py` | 07-04 |
| MOD-04 | Protocol, mock determinism, `source="mock"`, unavailable | unit | `... app/test_connectors.py` | 07-05 |
| MOD-05 | brief text, tenant-local date, disagreement, unavailable line, `due` | unit+DB | `... app/test_brief.py` | 07-05 |
| MOD-06 | check_reply codes, regenerate-once flow, never-post, rating-agnostic | unit+DB | `... app/test_reviews.py` | 07-06 |
| MOD-07 | mapping, 422 naming field, idempotent upsert, out-of-order | unit+DB | `... app/test_intake_event.py` | 07-07 |
| EVAL-05 | each module's case set passes | eval+pytest | `make g-eval-modules`; `... app/test_module_evals.py` | 07-08 |
| SEC (carry) | new tables RLS FORCE, grants, leak, coverage assert | DB | `... app/test_rls_proof.py app/test_leak.py` | 07-02 |
| Regression | roofing 94/96, dental 43/43 unchanged | eval | `make eval-gate`; `make g-eval ARGS="--pack bright-smile-dental --gate"` | existing baselines |

### Sampling Rate
- **Per task commit:** the plan's own test files (< 30 s, no LLM).
- **Per wave merge:** `make g-test` (full) once; run twice at the end of 07-08 (as Phase 6 did).
- **Phase gate:** full pytest green, `make g-eval-modules` 100%, roofing gate 94/96 same two failures, dental 43/43 (the baseline files exist).

### Wave 0 Gaps
- [ ] `tests_data/packs/demo-venue/*` fixture + `test_pack_modules.py` (07-01); pin roofing/dental pack hashes
- [ ] conftest: `apply_migrations` session fixture + cleanup for the 4 new tables (07-02)
- [ ] `evals/modules/` package and loader (07-08)
- [ ] Framework install: none

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `require_tenant` / `require_scope` (Phase 6 keys); no admin-key access to tenant module routes |
| V3 Session Management | no | stateless keys |
| V4 Access Control | yes | tenant from credential only; body `tenant_id` ignored; FORCE RLS on 4 new tables; approve/reject filtered by `tenant_id` AND RLS |
| V5 Input Validation | yes | pydantic `extra="forbid"` DTOs, size caps (email 4000, review 4000, intake payload 32 KB), aware datetimes only, dotted-path grammar |
| V6 Cryptography | no new | sha256 for input_hash (not security-bearing) |
| V7 Error handling/logging | yes | ids-only logs; 422 names field not value; connector errors rendered as type only |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via review/email text | Tampering | Delimited untrusted text; post-checks recompute truth; no tool selection by model |
| Model-invented price in quote email | Tampering | `check_quote_text` vs computed quote; needs_human on failure |
| Cross-tenant read via draft/flag/person ids | Info disclosure | RLS + `tenant_id` filters; 404 not 403; leak tests |
| PII in logs / events | Info disclosure | ids only; PII patterns in one module for Phase 9 masking |
| LLM cost abuse via module endpoints | DoS | per-tenant rate limit |
| Oversized payload / mapping abuse | DoS | size caps, closed dotted-path grammar, no list index or JSONPath |
| Replay of intake webhooks | Tampering | idempotent upsert, LEAST/ordering semantics |
| Auto-posting or auto-sending drafts | Repudiation | no send/post code in Phase 7; only `approved` marker |
| Health-data disclosure in review replies | Info disclosure | `health_privacy` rule; replies generic; demo/synthetic data only until legal review (carried from PITFALLS) |

## Sources

### Primary (HIGH confidence)
- Repo files read this session: `07-CONTEXT.md`, `.planning/REQUIREMENTS.md`, ROADMAP Phase 7, `.planning/research/SUMMARY.md`, `api/app/{pack,policy,auth,db,main,llm,tools,config,bootstrap,conftest,tenants,ratelimit}.py`, `test_rls_proof.py`, `test_leak.py`, `test_eval_gate.py` (head), `test_pack.py` (grep), `db/migrations/001-006`, `db/init.sql`, `evals/runner.py`, `Makefile`, `docker-compose.yml`, `businesses/*` YAMLs, Phase 6 summaries 02/03/04, spec sections on modules/workflows
- Local python runs (no repo writes): pack hashes; DST instants/window lengths for Denver and Zurich (2026-03-08, 2026-11-01, 2026-03-29, 2026-10-25), fold behaviour for gap/overlap times
- Spec `RoofDesk Global Platform Spec.md` (module table lines ~80-90, workflow catalog)

### Secondary (MEDIUM)
- https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/updateReply (Business Profile reply endpoint exists; verified location only), surfaced via WebSearch

### Tertiary (LOW)
- https://www.podium.com/online-reviews/review-gating/ and https://seologist.com/knowledge-sharing/what-is-review-gating-and-why-does-it-violate-googles-review-policies/ (review-gating rule described by vendors; Google's policy page itself not read)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (no new packages; everything read from the repo)
- Architecture/migration/RLS: HIGH (direct extension of 005 + Phase 6 tests)
- Quote/capacity/intake/brief designs: MEDIUM-HIGH (pure logic, concrete; interpretations flagged A7, Open Questions 1-3)
- Review heuristic and quote text extraction: MEDIUM (need fixture calibration)
- Pitfalls: MEDIUM-HIGH

**Research date:** 2026-11-04
**Valid until:** 2026-12-04 (stable internal codebase; re-check only if Phase 6 files change)
