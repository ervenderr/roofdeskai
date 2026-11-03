<!-- GSD:project-start source:PROJECT.md -->
## Project

**RoofDesk Global**

RoofDesk is an AI lead-booking agent (chat + voice) with evals, outbound, n8n workflows and a dashboard, today hardcoded to one business, Summit Roofing. RoofDesk Global makes it a multi-business platform: everything business-specific moves into a per-business config pack, so one agent, one set of n8n workflows and one eval suite serve any business. Roofing becomes pack #1.

Source spec: `RoofDesk Global Platform Spec.md` (Nov 3, 2026). Repo: `ervenderr/roofdeskai`, master.

**Core Value:** Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.

### Constraints

- **Regression gate**: `summit-roofing` stays at 94/96 with the same two failures until step 5 — eval is the safety net for every step
- **Architecture**: n8n triggers and sends; all decisions in FastAPI; platform must run without n8n
- **Determinism**: code computes numbers (quotes, capacity); model only writes text around them; evals deterministic
- **Simplicity**: smallest change per step; keep old code path until the rule interpreter passes
- **Live demo**: do not break roofdeskai.com; work on a branch
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Headline
## Recommended Additions
### Multi-tenancy and RLS (no new library)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Postgres RLS (built in) | existing PG | Isolation on `tenant_id` | Policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)` on leads, slots, conversations, FAQ rows. |
| SQLAlchemy `set_config` per transaction | existing 2.x | Carry tenant into the DB | Run `SELECT set_config('app.tenant_id', :t, true)` (third arg `true` = transaction-local) at the start of each `engine.begin()`. Transaction-local is mandatory because `create_engine` pools connections; a session-level `SET` leaks one tenant's id to the next request. |
| Plain numbered SQL migrations in `db/` | n/a | Schema change on the live DB | `db/init.sql` only runs on a fresh volume; the live demo DB needs `ALTER TABLE` scripts. Apply them from the existing `bootstrap.py`. Do NOT add Alembic for ~4 migrations. |
- The app must connect as a non-superuser role that does not own the tables. Superusers and table owners bypass RLS. Otherwise use `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. Keep a separate owner role for migrations.
- Put a single helper (`tenant_conn(tenant_id)`) in `db.py`. Every request path uses it; no raw `engine.begin()` in tenant code (the 3 existing call sites in `bootstrap.py`, `pilot.py`, tests need an explicit decision: admin/system context vs tenant context).
- pgvector table (FAQ): RLS applies, but add `tenant_id` to the similarity query's index strategy. A global HNSW index with tenant filtering returns fewer than k rows after filtering. At pack scale (tens of facts per tenant) this is irrelevant; do not partition.
### Pack loading and validation (no new library)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pyyaml` `yaml.safe_load` | 6.0.3 (latest; pin `6.*` ok) | Read pack YAML | Already used for `clients/*.yaml`. Always `safe_load`. |
| Pydantic v2 models, `ConfigDict(extra="forbid")` | 2.14.x latest (pin `2.*` ok) | Validate packs | `extra="forbid"` turns YAML typos into load errors, which is what `make new-business` needs. |
| Pydantic discriminated union on `rule` | same | Rule types as data | `Annotated[InList \| YesNo \| MaxNumber \| InArea, Field(discriminator="rule")]`. Unknown rule type fails at load, not at chat time. |
| `decimal.Decimal` (stdlib) | n/a | Prices, quote totals | Never float for money. Pydantic validates `Decimal` fields natively. Quantize once at the total. |
| `zoneinfo` (stdlib) + **`tzdata`** | tzdata latest | Tenant-local time for daily-brief, slots | `python:3.12-slim` has no system tz database; `ZoneInfo("America/Denver")` raises without the `tzdata` pip package. |
### Rule interpreter, quote builder, capacity checker (no new library)
| Capability | Implementation | Why not a library |
|-----------|----------------|-------------------|
| Qualification interpreter | `dict[type, Callable]` dispatch over the 4 rule types (`in_list`, `yes_no`, `max_number`, `in_area`) | `json-logic`, `rule-engine`, `durable_rules` bring a DSL you do not need and make the 94/96 regression gate harder to reason about. Four pure functions beat a DSL. |
| Quote builder | Pure functions over `Decimal`; missing price returns a typed `NeedsHuman`, never a guess | Matches "code computes numbers". |
| Capacity checker | Pure functions over dataclasses; interval overlap with stdlib `datetime` | Rota rules are simple; `ortools`/`pulp` is overkill. |
### Connector layer as MCP servers
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `mcp` (official Python SDK) | **2.3.0** (latest on PyPI; 2.0 GA, 2.1/2.2/2.3 since) | Expose connectors as MCP tools | Official SDK, Python >=3.10 (works on your 3.12 image). Requires `pydantic>=2.12`, which `pydantic==2.*` already resolves to. |
- `FastMCP` is now `MCPServer`, imported from `mcp.server.mcpserver`. `from mcp.server.fastmcp import FastMCP` raises `ModuleNotFoundError`. Most web examples are v1 and wrong.
- Pass all constructor args except `name` by keyword (positional order changed; `instructions` silently lands in `title`).
- Transport settings moved from the constructor to `run()` / `streamable_http_app()`.
- When mounting the streamable-HTTP app inside FastAPI you must start `mcp.session_manager` in the host app's lifespan, or you get `RuntimeError: Task group is not initialized`. Build the app at module level.
- DNS-rebinding protection is on for localhost; a request whose `Host` has no port gets `421`. Configure `transport_security` for real hostnames.
- It depends on **`httpx2`**, a separate package from your `httpx==0.27.*`. They coexist; do not "fix" by bumping `httpx`.
### Anthropic provider in the LLM chain
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Anthropic OpenAI-compat endpoint via existing `openai` SDK | `openai==1.*` (existing) | Add Claude as a `Provider` | `llm.py` is a list of OpenAI-compatible `Provider(name, base_url, api_key, model)`. Adding `Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, "<model>")` is a 1-line change and zero new dependencies. |
| `anthropic` native SDK | 2.4.0 | Only if you need native features | Not needed for this milestone. |
- Claude 4.7+ models return 400 for `temperature` below 1 and for `top_p` other than the default. If `_call` sends `temperature=0` for determinism, make it per-provider (omit for anthropic). Check `_call` before wiring; I did not read lines 40-52.
- `response_format` accepts only `json_schema` with `strict: true`; `json_object` returns 400. If the agent uses `json_object`, anthropic will 400 on every call. Your chain treats `BadRequestError` as "try next provider, no cooldown", so this would silently fall through and make the scorecard meaningless. Either send `json_schema` or log loudly.
- `tool_choice` "required"/named function returns 400 on Sonnet 5.5 / Opus 5.5; use `auto`.
- No prompt caching, no thinking text, `n` must be 1, system messages are hoisted.
- Do not put anthropic first in `PROVIDERS` by default (local stays default). For the scorecard, run evals with an explicit `providers=[anthropic]` list (`chat()` already accepts one) so fallbacks cannot contaminate the score.
- Model IDs: docs list `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-sonnet-5-5` etc. Pick the model from a setting, not a constant. Cost is unmeasured; use a cheap tier for eval runs.
### Per-tenant API keys (stdlib only)
| Technology | Purpose | Why |
|------------|---------|-----|
| `secrets.token_urlsafe(32)` | Generate keys with a prefix (`rd_live_...`) | High-entropy random keys. |
| `hashlib.sha256` | Store only the hash in `tenant_api_keys(tenant_id, key_hash, label, revoked_at)` | Fast hash is correct for 256-bit random secrets; bcrypt/argon2 (`passlib`) is for human passwords. |
| `hmac.compare_digest` | Compare | Already used in `admin.py`. |
| FastAPI `Depends` on `X-API-Key` header | Resolves tenant, then opens `tenant_conn(tenant_id)` | Same style as `require_admin`. Keep `X-Admin-Key` as a separate super-admin scope (tenant CRUD, cross-tenant metrics). |
### PII masking in logs (stdlib only)
| Technology | Purpose | Why |
|------------|---------|-----|
| `logging.Filter` installed on the root handler, regexes for email, phone, and a street-address heuristic | Mask before records are emitted | The code uses stdlib `logging` (`logging.getLogger("leadpilot.llm")`), so a filter covers all modules including third parties. |
### Docs generation
| Library | Version | Purpose | When |
|---------|---------|---------|------|
| `jinja2` | 3.x (verify latest at install; not checked) | One SOP per workflow + runbook from pack data | Only if SOP templates have loops/conditionals. If 12 short templates, `str.format`/`string.Template` is enough. Run it as a dev/CLI-time tool, not an API dependency. |
### n8n (no new library)
- Do not add n8n community nodes or custom code nodes for tenant logic. Pass tenant via the per-tenant `X-API-Key` header on every HTTP Request node; store each tenant's key in an n8n credential (Header Auth) and select it from the incoming webhook's tenant id.
- Scheduled workflows (nightly, daily-brief at tenant-local time) should call one API endpoint that lists tenants and their timezones (`GET /admin/tenants`), then loop with Split In Batches. Cron-per-tenant duplicates workflows; avoid it. The API, not n8n, decides whether "now" is the tenant's local morning (one endpoint `POST /daily-brief/due` returning the tenants to run), consistent with "n8n triggers and sends".
- Workflow JSON lives in `n8n/workflows/`; keep exporting it. Add a CI check that fails if any HTTP node to the API lacks the key header.
- License: n8n is Sustainable Use License (fair-code). Already flagged in PROJECT.md; no stack change now.
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
# api/requirements.txt additions
# optional, only if SOP templates need logic
## What NOT to add (summary)
## Open items to verify during implementation
## Sources
- PyPI JSON API (versions checked 2026-11-03): mcp 2.3.0 (requires pydantic>=2.12, httpx2>=2.10), anthropic 2.4.0, pydantic 2.14.2, pyyaml 6.0.3, psycopg 3.3.7, sqlalchemy 2.1.6, presidio-analyzer 2.2.366, structlog 26.1.0
- https://py.sdk.modelcontextprotocol.io/migration/ (official MCP Python SDK v1 to v2 migration; first ~100k chars read) HIGH
- https://github.com/modelcontextprotocol/python-sdk (README: `MCPServer`, Python 3.11+ stated in README vs `>=3.10` in PyPI metadata; your 3.12 image satisfies both) HIGH
- https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk (Anthropic OpenAI SDK compatibility, base URL and limitations) HIGH
- Repo inspection: `api/requirements.txt`, `api/app/llm.py` (lines 1-35, 53-66), `api/app/admin.py`, `api/app/db.py`, Dockerfiles (python:3.12-slim)
- Postgres RLS and `set_config(..., true)` behaviour from training knowledge, not re-fetched this session: MEDIUM-HIGH
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
