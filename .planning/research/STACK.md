# Technology Stack (additions only)

**Project:** RoofDesk Global (multi-tenant config-pack platform)
**Researched:** 2026-11-03
**Scope:** Only NEW capabilities. Existing FastAPI 0.115, Pydantic 2, SQLAlchemy 2 + psycopg 3.2, pyyaml 6, openai 1.x, httpx 0.27, pytest 8, Postgres/pgvector, Docker (python:3.12-slim), n8n, Next.js are kept as is.

## Headline

Net new runtime dependencies: **`mcp` (and `tzdata`)**. Optionally `jinja2` (SOP generation). Everything else is Postgres features, Pydantic features you already have, or stdlib. No ORM migration tool, no rules engine, no PII/NLP library, no auth framework.

## Recommended Additions

### Multi-tenancy and RLS (no new library)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Postgres RLS (built in) | existing PG | Isolation on `tenant_id` | Policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)` on leads, slots, conversations, FAQ rows. |
| SQLAlchemy `set_config` per transaction | existing 2.x | Carry tenant into the DB | Run `SELECT set_config('app.tenant_id', :t, true)` (third arg `true` = transaction-local) at the start of each `engine.begin()`. Transaction-local is mandatory because `create_engine` pools connections; a session-level `SET` leaks one tenant's id to the next request. |
| Plain numbered SQL migrations in `db/` | n/a | Schema change on the live DB | `db/init.sql` only runs on a fresh volume; the live demo DB needs `ALTER TABLE` scripts. Apply them from the existing `bootstrap.py`. Do NOT add Alembic for ~4 migrations. |

Rules that matter:
- The app must connect as a non-superuser role that does not own the tables. Superusers and table owners bypass RLS. Otherwise use `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. Keep a separate owner role for migrations.
- Put a single helper (`tenant_conn(tenant_id)`) in `db.py`. Every request path uses it; no raw `engine.begin()` in tenant code (the 3 existing call sites in `bootstrap.py`, `pilot.py`, tests need an explicit decision: admin/system context vs tenant context).
- pgvector table (FAQ): RLS applies, but add `tenant_id` to the similarity query's index strategy. A global HNSW index with tenant filtering returns fewer than k rows after filtering. At pack scale (tens of facts per tenant) this is irrelevant; do not partition.

Confidence: HIGH on RLS mechanics (core Postgres behaviour); MEDIUM on the pooled-connection details (verify with one cross-tenant test in CI).

### Pack loading and validation (no new library)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pyyaml` `yaml.safe_load` | 6.0.3 (latest; pin `6.*` ok) | Read pack YAML | Already used for `clients/*.yaml`. Always `safe_load`. |
| Pydantic v2 models, `ConfigDict(extra="forbid")` | 2.14.x latest (pin `2.*` ok) | Validate packs | `extra="forbid"` turns YAML typos into load errors, which is what `make new-business` needs. |
| Pydantic discriminated union on `rule` | same | Rule types as data | `Annotated[InList \| YesNo \| MaxNumber \| InArea, Field(discriminator="rule")]`. Unknown rule type fails at load, not at chat time. |
| `decimal.Decimal` (stdlib) | n/a | Prices, quote totals | Never float for money. Pydantic validates `Decimal` fields natively. Quantize once at the total. |
| `zoneinfo` (stdlib) + **`tzdata`** | tzdata latest | Tenant-local time for daily-brief, slots | `python:3.12-slim` has no system tz database; `ZoneInfo("America/Denver")` raises without the `tzdata` pip package. |

Do NOT add: `ruamel.yaml` (round-trip comments are not needed; the knowledge-gap loop that writes `knowledge.yaml` is a backlog item, not this milestone), `pydantic-yaml`, `dynaconf`, Hydra.

Cross-file validation (e.g. `services.yaml` referenced from `qualification.yaml`, `connectors.yaml` names exist) goes in a single `Pack` root model with `model_validator(mode="after")`.

Confidence: HIGH.

### Rule interpreter, quote builder, capacity checker (no new library)
| Capability | Implementation | Why not a library |
|-----------|----------------|-------------------|
| Qualification interpreter | `dict[type, Callable]` dispatch over the 4 rule types (`in_list`, `yes_no`, `max_number`, `in_area`) | `json-logic`, `rule-engine`, `durable_rules` bring a DSL you do not need and make the 94/96 regression gate harder to reason about. Four pure functions beat a DSL. |
| Quote builder | Pure functions over `Decimal`; missing price returns a typed `NeedsHuman`, never a guess | Matches "code computes numbers". |
| Capacity checker | Pure functions over dataclasses; interval overlap with stdlib `datetime` | Rota rules are simple; `ortools`/`pulp` is overkill. |

Confidence: HIGH (design judgment, not an ecosystem fact).

### Connector layer as MCP servers
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `mcp` (official Python SDK) | **2.3.0** (latest on PyPI; 2.0 GA, 2.1/2.2/2.3 since) | Expose connectors as MCP tools | Official SDK, Python >=3.10 (works on your 3.12 image). Requires `pydantic>=2.12`, which `pydantic==2.*` already resolves to. |

Use `pip install "mcp"` and pin `mcp==2.3.*`. Not `mcp[cli]` in the image (only adds typer/rich/dotenv for dev tooling).

**Breaking changes vs. the v1 tutorials/blog posts you will find (verified in the official migration guide, https://py.sdk.modelcontextprotocol.io/migration/):**
- `FastMCP` is now `MCPServer`, imported from `mcp.server.mcpserver`. `from mcp.server.fastmcp import FastMCP` raises `ModuleNotFoundError`. Most web examples are v1 and wrong.
- Pass all constructor args except `name` by keyword (positional order changed; `instructions` silently lands in `title`).
- Transport settings moved from the constructor to `run()` / `streamable_http_app()`.
- When mounting the streamable-HTTP app inside FastAPI you must start `mcp.session_manager` in the host app's lifespan, or you get `RuntimeError: Task group is not initialized`. Build the app at module level.
- DNS-rebinding protection is on for localhost; a request whose `Host` has no port gets `421`. Configure `transport_security` for real hostnames.
- It depends on **`httpx2`**, a separate package from your `httpx==0.27.*`. They coexist; do not "fix" by bumping `httpx`.

Integration design (opinionated):
1. Write each connector (`sheet`, `accounting`, `bookings`, `ads`, `supplier`) as a plain Python class with a mock implementation, in `api/app/connectors/`. The daily-brief and the API call these classes **directly, in-process**. MCP is not on the hot path.
2. Add one thin `MCPServer` per connector (or one server with namespaced tools) that wraps the same classes. Run it over streamable HTTP mounted in FastAPI, or as a stdio entry point (`python -m app.connectors.mcp_sheet`) for Claude Desktop/Claude Code demos.
3. Tenant scoping: MCP tools take the tenant from the authenticated request (per-tenant key), never from a tool argument the model could set. For the stdio demo, bind tenant via env var at process start.
4. Test with the SDK's in-process client; v2 removed `create_connected_server_and_client_session`, and the replacement is in the migration guide's Testing section, which I did not finish reading. Check it before writing connector tests. If it is awkward, test the plain connector classes (where the logic lives) and add one HTTP smoke test.

Confidence: HIGH on version and v2 renames (PyPI + official migration guide); MEDIUM on the mounting details (read the guide's ASGI section when implementing); LOW on the v2 test-client replacement (not read).

### Anthropic provider in the LLM chain
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Anthropic OpenAI-compat endpoint via existing `openai` SDK | `openai==1.*` (existing) | Add Claude as a `Provider` | `llm.py` is a list of OpenAI-compatible `Provider(name, base_url, api_key, model)`. Adding `Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, "<model>")` is a 1-line change and zero new dependencies. |
| `anthropic` native SDK | 2.4.0 | Only if you need native features | Not needed for this milestone. |

**Why compat layer despite Anthropic calling it "not production-ready for most use cases":** your feature is a side-by-side scorecard and an optional provider, which is exactly the "test and compare" use the docs describe. Adopt the native SDK later if it goes to paid production.

Limits to code around (official doc, https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk):
- Claude 4.7+ models return 400 for `temperature` below 1 and for `top_p` other than the default. If `_call` sends `temperature=0` for determinism, make it per-provider (omit for anthropic). Check `_call` before wiring; I did not read lines 40-52.
- `response_format` accepts only `json_schema` with `strict: true`; `json_object` returns 400. If the agent uses `json_object`, anthropic will 400 on every call. Your chain treats `BadRequestError` as "try next provider, no cooldown", so this would silently fall through and make the scorecard meaningless. Either send `json_schema` or log loudly.
- `tool_choice` "required"/named function returns 400 on Sonnet 5.5 / Opus 5.5; use `auto`.
- No prompt caching, no thinking text, `n` must be 1, system messages are hoisted.
- Do not put anthropic first in `PROVIDERS` by default (local stays default). For the scorecard, run evals with an explicit `providers=[anthropic]` list (`chat()` already accepts one) so fallbacks cannot contaminate the score.
- Model IDs: docs list `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-sonnet-5-5` etc. Pick the model from a setting, not a constant. Cost is unmeasured; use a cheap tier for eval runs.

Confidence: HIGH (read official page).

### Per-tenant API keys (stdlib only)
| Technology | Purpose | Why |
|------------|---------|-----|
| `secrets.token_urlsafe(32)` | Generate keys with a prefix (`rd_live_...`) | High-entropy random keys. |
| `hashlib.sha256` | Store only the hash in `tenant_api_keys(tenant_id, key_hash, label, revoked_at)` | Fast hash is correct for 256-bit random secrets; bcrypt/argon2 (`passlib`) is for human passwords. |
| `hmac.compare_digest` | Compare | Already used in `admin.py`. |
| FastAPI `Depends` on `X-API-Key` header | Resolves tenant, then opens `tenant_conn(tenant_id)` | Same style as `require_admin`. Keep `X-Admin-Key` as a separate super-admin scope (tenant CRUD, cross-tenant metrics). |

Do NOT add: Clerk, Auth0, `fastapi-users`, `authlib` in this milestone. Clerk is for dashboard login and is a separate, later item; machine-to-machine tenant keys do not need it. Do not store a tenant id in a client-supplied header on its own (the `X-Tenant` header is only trustworthy if the key is what proves it).

Confidence: HIGH.

### PII masking in logs (stdlib only)
| Technology | Purpose | Why |
|------------|---------|-----|
| `logging.Filter` installed on the root handler, regexes for email, phone, and a street-address heuristic | Mask before records are emitted | The code uses stdlib `logging` (`logging.getLogger("leadpilot.llm")`), so a filter covers all modules including third parties. |

Why not `presidio-analyzer` (2.2.366): it pulls spaCy and a model download (hundreds of MB) into a slim image, adds latency per log line, and still misses names unpredictably. Why not `structlog` (26.1.0): a logging rewrite for a masking feature. Names: the structured fields you control (`lead.name`) should not be logged at all; mask at the call site. Regex masking catches emails and phones, not free-text names in chat transcripts; state that limit in the data-map doc rather than overpromising.

Also mask: dashboard/Agent Office payloads (separate concern, same helper, expose it as a pure function `mask(text) -> str` and unit test it).

Confidence: MEDIUM-HIGH (design judgment; regex-only limits are well known).

### Docs generation
| Library | Version | Purpose | When |
|---------|---------|---------|------|
| `jinja2` | 3.x (verify latest at install; not checked) | One SOP per workflow + runbook from pack data | Only if SOP templates have loops/conditionals. If 12 short templates, `str.format`/`string.Template` is enough. Run it as a dev/CLI-time tool, not an API dependency. |

Confidence: LOW-MEDIUM on version (not verified); the recommendation itself is optional.

### n8n (no new library)
- Do not add n8n community nodes or custom code nodes for tenant logic. Pass tenant via the per-tenant `X-API-Key` header on every HTTP Request node; store each tenant's key in an n8n credential (Header Auth) and select it from the incoming webhook's tenant id.
- Scheduled workflows (nightly, daily-brief at tenant-local time) should call one API endpoint that lists tenants and their timezones (`GET /admin/tenants`), then loop with Split In Batches. Cron-per-tenant duplicates workflows; avoid it. The API, not n8n, decides whether "now" is the tenant's local morning (one endpoint `POST /daily-brief/due` returning the tenants to run), consistent with "n8n triggers and sends".
- Workflow JSON lives in `n8n/workflows/`; keep exporting it. Add a CI check that fails if any HTTP node to the API lacks the key header.
- License: n8n is Sustainable Use License (fair-code). Already flagged in PROJECT.md; no stack change now.

Confidence: MEDIUM (n8n node-level specifics not re-verified against current n8n docs).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Tenant isolation | Postgres RLS + `set_config` | Schema-per-tenant, DB-per-tenant | Spec asks for RLS; far less ops for a handful of packs |
| Tenant isolation | RLS | App-layer `WHERE tenant_id` only | One forgotten filter leaks data; RLS is the backstop |
| Migrations | Numbered SQL via `bootstrap.py` | Alembic | Overhead for ~4 changes; revisit if schema churn grows |
| Rule interpreter | Pydantic union + dispatch dict | json-logic / rule-engine / OPA | DSL + dependency for four rules; harder to eval deterministically |
| Pack validation | Pydantic | JSON Schema / Cerberus | Pydantic already in the repo, gives typed objects |
| MCP | official `mcp` 2.3 | `fastmcp` (jlowin, standalone) | Standalone project has its own API and versioning; official SDK is enough and the spec names "Python MCP SDK" |
| Claude access | OpenAI-compat endpoint | `anthropic` SDK + adapter | Adapter code to translate messages/tools for a scorecard-only feature |
| API keys | sha256 + `secrets` | passlib/bcrypt, Clerk | Wrong tool for machine keys |
| PII | stdlib filter + regex | Presidio, structlog | Heavy images, NLP models, partial wins |
| Money | `Decimal` | float, `py-moneyed` | Single currency per pack; Decimal suffices |

## Installation

```bash
# api/requirements.txt additions
mcp==2.3.*
tzdata
# optional, only if SOP templates need logic
jinja2==3.*
```

No dashboard (Next.js) or n8n package changes.

## What NOT to add (summary)
Alembic, Presidio, structlog, passlib, Clerk/Auth0 for machine keys, any rules engine, ortools, ruamel.yaml, the `anthropic` SDK (for now), `fastmcp` standalone, Redis/Celery (n8n triggers the schedules), a second vector DB.

## Open items to verify during implementation
1. Lines 40-52 of `api/app/llm.py` (`_call`): does it send `temperature` / `response_format=json_object`? Both break against Anthropic's compat layer.
2. v2 `mcp` in-process test client replacement (migration guide, Testing section).
3. Current `jinja2` and `tzdata` versions at install time.
4. Which DB role the app uses today (`docker-compose.yml` / `DATABASE_URL`). If it is the owner or `postgres`, RLS will not enforce until a restricted role is created. This is the most likely silent RLS failure.
5. All raw `engine.begin()` call sites in `api/app` (bootstrap, pilot, tests) need classification as system vs tenant context.

## Sources

- PyPI JSON API (versions checked 2026-11-03): mcp 2.3.0 (requires pydantic>=2.12, httpx2>=2.10), anthropic 2.4.0, pydantic 2.14.2, pyyaml 6.0.3, psycopg 3.3.7, sqlalchemy 2.1.6, presidio-analyzer 2.2.366, structlog 26.1.0
- https://py.sdk.modelcontextprotocol.io/migration/ (official MCP Python SDK v1 to v2 migration; first ~100k chars read) HIGH
- https://github.com/modelcontextprotocol/python-sdk (README: `MCPServer`, Python 3.11+ stated in README vs `>=3.10` in PyPI metadata; your 3.12 image satisfies both) HIGH
- https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk (Anthropic OpenAI SDK compatibility, base URL and limitations) HIGH
- Repo inspection: `api/requirements.txt`, `api/app/llm.py` (lines 1-35, 53-66), `api/app/admin.py`, `api/app/db.py`, Dockerfiles (python:3.12-slim)
- Postgres RLS and `set_config(..., true)` behaviour from training knowledge, not re-fetched this session: MEDIUM-HIGH
