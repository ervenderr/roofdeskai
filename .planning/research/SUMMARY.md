# Project Research Summary

**Project:** RoofDesk Global (multi-tenant config-pack platform)
**Domain:** Multi-business AI front-desk platform (lead agent, quotes, capacity, review replies, owner brief, intake) for SMB service and venue businesses
**Researched:** 2026-11-03
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a retrofit, not a greenfield build. A working single-tenant roofing lead agent (FastAPI, Postgres/pgvector, local Ollama, n8n, 94/96 eval baseline) becomes a platform where a business is a validated YAML "pack". The pattern is "model proposes, code decides": the LLM extracts and phrases; qualification, quotes, capacity and brief numbers come from pure deterministic code driven by the pack.

Approach:
- One seam: a Pydantic `Pack` (`extra="forbid"`) resolved per tenant.
- Move roofing constants into it verbatim; data move and logic swap are separate gated steps.
- Net new dependencies: `mcp==2.3.*` and `tzdata` (optionally `jinja2`).
- Isolation: Postgres RLS with transaction-local `set_config`, numbered SQL migrations, sha256-hashed per-tenant API keys.
- No Alembic, rules engine, Presidio or Clerk.

Main risks are silent failures: RLS doing nothing if the app connects as owner/superuser; eval parity hiding behind an aggregate 94/96; default-tenant fallback leaking across businesses; roofing coupling hidden in `prompts/agent.v2.md`, `policy.py` stopwords and `ensure_slots`.

## Key Findings

### Recommended Stack (STACK.md)

- **Postgres RLS + `set_config('app.tenant_id', :t, true)`**: transaction-local is mandatory with pooling. App role non-owner, no BYPASSRLS, plus `FORCE ROW LEVEL SECURITY`.
- **Numbered SQL migrations + `schema_migrations`, run from `bootstrap.py`**: `init.sql` only runs on an empty volume.
- **Pydantic v2 + `yaml.safe_load`**: discriminated union on `rule`; bad packs fail at load.
- **`Decimal` + `zoneinfo` + `tzdata`**: money and tenant-local time (slim image has no tz database).
- **Dispatch dict over 4 rule types, pure quote/capacity functions**.
- **`mcp==2.3.*` (v2 API: `MCPServer`, not `FastMCP`)**: connectors are plain classes called in-process; MCP is a thin wrapper.
- **Anthropic via existing `openai` SDK compat endpoint**: `temperature`, `json_object`, forced `tool_choice` can return 400, and a 400 falls through the chain silently. Evals must pin `providers=[anthropic]`.
- **`secrets` + sha256 + `hmac.compare_digest`**: per-tenant keys; admin key a separate scope.
- **stdlib `logging.Filter` + pure `mask()`**: PII masking.

### Expected Features (FEATURES.md)

**Must have:** pack loader/validation; tenant isolation; data-driven qualification (4 rule types) reproducing roofing exactly; pack-driven FAQ/escalation (recall stays 100%); quote builder (code-computed, missing price escalates, approval before send); capacity checker (idempotent re-flag, dedupe); review responder (draft-only, deterministic guardrails); connector layer with mocks; daily owner brief (tenant-local time, "source unavailable" visible); intake-event webhook (idempotent); tenant-aware n8n; per-tenant keys + RLS; `make new-business`; per-pack scorecard; PII masking/retention/data map; generated SOPs.

**Should have:** source-disagreement flags in brief; held-out 20 scenarios published even if low; MCP connectors; local vs Anthropic scorecard; group/corporate quote rules; third (venue) pack.

**Defer:** real connectors/write actions; multi-language; real SMS/phone; review-request workflow and knowledge-gap loop; supplier-order, Agent Office, Flight Recorder (cut first).

### Architecture Approach (ARCHITECTURE.md)

`Pack` is the single seam. State machine, grounding, retry, LLM chain and tool logging stay.
- Pass `tenant_id` explicitly; route all DB access through one `db.tx(tenant_id)` helper from step 2.
- Engine modules are pure functions of (pack, input).
- n8n only triggers and sends; platform must run without it.
- Leave `intake.py` (RoofDesk's own sales funnel), `outreach`, `replies`, `pilot` untenanted. Name the new webhook `intake_event` to avoid colliding with `/intake`.

Components: `app/pack.py` + `businesses/<slug>/*.yaml`; `app/tenants.py` + `db.tx()`; `qualify.py`; `engine/*`; `connectors/` + `mcp_server.py`; `agent_events` + migrations.

Hidden roofing coupling to fix: `prompts/agent.v2.md` (extraction schema + example; roofing render must be byte-identical); `policy._GENERIC` stopwords, `_CLAIM_RE` (blocks quoted prices), `SAFE_FALLBACK`; `agent.py` strings; `tools.ensure_slots` (silently skips tenant 2 slots); `faq.seed_faq` early return; `admin.py` global metrics; `evals/runner.py` overwrites `latest.md`; global uniques on `appointments` and `conversations.external_id`.

### Critical Pitfalls (PITFALLS.md)

1. **RLS silently bypassed (owner/superuser)**: separate `migrator`/`app` roles, FORCE RLS, test that no-tenant query returns 0 rows; run pytest on an RLS-enabled DB from step 2.
2. **Aggregate-only eval gate**: gate on per-scenario-id diff against a frozen JSON baseline; measure flake over 3 runs; pin model tag/temperature; differential old-vs-interpreter test; prompt byte-identity test.
3. **Default-tenant fallback / body-supplied tenant ids**: default only in backfill, then drop; derive tenant from credential; issue keys before exposing tenant-aware n8n.
4. **tenant_id retrofit misses uniques, FKs, slots, pgvector**: composite constraints; tenant filter in vector query and RLS; reload FAQ by delete-then-insert; cross-tenant retrieval eval.
5. **Globals/caches and regex-to-data drift**: immutable pack passed explicitly; cache keys include tenant + pack hash; port regexes verbatim first; no DSL.
6. **Breaking the live demo**: expand/contract migrations; separate compose project/volume; rehearse on DB copy; ask before any deploy. Repo is `master`, spec says `main` — confirm.
7. **PII/data protection**: tenant-stamped logs, masking filter, retention that really deletes; dental is demo-only with synthetic data until health-data handling is addressed; legal review before any real Swiss/EU customer.

## Implications for Roadmap

Spec's steps with four reorderings: split pack extraction into data-move and rewire; per-pack eval runner before dental; `db.tx()` + migration runner in step 2; per-tenant keys before exposing tenant-aware n8n.

### Phase 1: Baseline Freeze and Environment Isolation
Tag `v1-roofing`; per-scenario baseline JSON; 3x flake measurement, pinned model; isolated compose project/volume; inventory roofing assumptions (read `intake.py`, `prompts/`).

### Phase 2: Tenants, Migrations and DB Plumbing
Migration runner + `schema_migrations`; `tenants` with seeded default; `tenant_id` + composite uniques/FKs; `db.tx()`, non-owner `app` role, RLS on test DB; tenant-stamped logging; `agent_events`; tenant-aware `ensure_slots` and FAQ seed; outbound stays untenanted.

### Phase 3: Pack Loader and Extraction (3a data move, 3b rewire)
3a: `Pack` models, summit-roofing YAML, golden test pack values == old constants. 3b: rewire call sites, template prompts (byte-identical roofing render), remove globals, `pack_version` on conversations.

### Phase 4: Rule Interpreter
`qualify.py` with 4 rule types; dual-run differential test over a large lead grid (`address_status` ported unchanged as `in_area`); switch `policy` and runner; relax `ServiceType` enum (keep fixed `LeadFields`); delete old path after zero diffs.

### Phase 5: Per-Pack Eval Runner and Dental Pack
`--pack` runner and per-pack reports; dental pack (~40 scenarios, `always_human` emergency categories); two-tenant interleaved test, cross-tenant retrieval and prompt-injection scenarios; no category under 90%, safety recall 100%.

### Phase 6: Per-Tenant Keys and RLS Enforcement
`tenant_api_keys` (hashed, shown once, rotation, revoke); key-based resolver; admin key separate scope; RLS FORCE on all tenant tables, drop column DEFAULT, 401 without key; leak test across chat/FAQ/slots/metrics; `admin.py` audit.

### Phase 7: Engine Modules and Connectors
In order: quote builder (Decimal, approval queue, bypass `_CLAIM_RE`, missing price escalates); capacity checker (dedupe, DST tests); connector interface + mocks; daily brief (tenant tz, disagreement flags); review responder (draft-only guardrails, health-privacy block); `intake_event`. Anthropic provider any time after Phase 1.

### Phase 8: Tenant-Aware n8n
Update 6 existing workflows (key header, owner address from API); 5 new workflows (supplier-order is cut-first); `GET /admin/tenants` loop with API deciding "due now"; CI check that API HTTP nodes carry the key header; API-only run test; execution-data pruning; license decision.

### Phase 9: Docs, PII/Retention, `make new-business`
Masking filter; retention purge across stores + `delete_subject`; data map; SOPs generated in CI with drift check; `make new-business` (validate, load, smoke, cross-tenant and escalation baselines); grep gate for `roof|Summit|Denver` in shared code.

### Phase 10: Held-Out Eval, Then Optional Items
20 held-out scenarios run once and published (including the 2 known failures). Then MCP wrapper, Anthropic scorecard, third (venue) pack. Cut first: supplier-order, Agent Office, Flight Recorder.

### Research Flags
**Needs deeper research:** Phase 2 (DB role, ~40 `engine.begin()` call sites, composite FK inventory, pool-size-1 RLS test); Phase 4 (regex inventory, differential corpus); Phase 7 (module designs, Google review policy, `llm._call` params, MCP v2 mounting/test client); Phase 8 (n8n specifics, license); Phase 9 (nFADP/GDPR, Gemini terms).
**Standard patterns:** Phases 1, 3, 5, 6, 10.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI + official docs; MEDIUM on MCP mounting, LOW on v2 test client; RLS from training knowledge |
| Features | MEDIUM | Spec-grounded; no live competitor pages |
| Architecture | HIGH integration / MEDIUM modules | Read from actual code |
| Pitfalls | MEDIUM | No live verification |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address
- Which DB role the app uses today (owner/`postgres` means RLS won't enforce) — Phase 2.
- `api/app/llm.py` `_call` lines 40-52 unread — check before Anthropic wiring.
- Eval flake rate unknown — measure in Phase 1.
- Deploy branch: `master` vs spec's `main`.
- Dental health-data handling and cross-border LLM transfer — decide Phase 5, document Phase 9, legal review before real EU/CH customers.
- n8n licensing for customer-hosted scenarios; pgvector/Postgres versions unverified.
- Mock connectors hide real API behavior — label them as mock.

## Sources
**Primary:** PyPI JSON API (2026-11-03); MCP python-sdk migration guide; Anthropic OpenAI-SDK compat docs; repo code (`policy`, `faq`, `agent`, `tools`, `intake`, `schemas`, `main`, `bootstrap`, `admin`, `db`, `init.sql`, `prompts/`, `clients/`, `evals/runner.py`, `docker-compose.yml`, n8n workflows); `.planning/PROJECT.md`; the platform spec.
**Secondary (MEDIUM):** Postgres row security docs, pgvector filtering, n8n Sustainable Use License, Google Business Profile review policy (prior knowledge, not re-fetched).
**Tertiary (LOW):** competitor analysis, GDPR Art. 9 / nFADP specifics, Gemini free-tier terms.

*Research completed: 2026-11-03*
*Ready for roadmap: yes*
