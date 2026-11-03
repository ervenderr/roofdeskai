# Architecture Patterns

**Domain:** Multi-tenant config-pack retrofit of a single-business FastAPI lead agent
**Researched:** 2026-11-03 (read from the actual code: policy, faq, agent, tools, intake, triage, schemas, main, bootstrap, init.sql, prompts/, clients/, evals/runner.py, docker-compose.yml, n8n workflow URLs)
**Confidence:** HIGH on integration points (read from code), MEDIUM on module designs (not yet built)

## Recommended Architecture

Add one seam: a `Pack` object (Pydantic-validated, loaded from `businesses/<slug>/`) resolved per request from a tenant. Everything business-specific is read from it. The state machine, grounding, retry, LLM chain and tool-logging stay as they are.

```
request (/chat, /webhooks/inbound, ...)  ->  tenant resolver (default tenant until step 8)
   -> packs.get(tenant_id) -> Pack (cached, immutable)
   -> agent.handle_turn(message, cid, ..., pack)   # pack threaded through _decide
        policy.qualification(lead, pack.qualification)   # rule interpreter
        tools.*(..., tenant_id)                           # tenant-scoped SQL
        messages/ASK/FAQ/slots from pack
   -> engine modules (quote, capacity, review, brief, intake_event) take pack, return dicts
   -> connectors (adapters + mocks) <- same adapters wrapped as MCP servers
   -> agent_events (append-only) written by agent + modules
n8n: triggers, passes tenant_id, sends. No decisions.
```

### Component Boundaries

| Component | Status | Responsibility | Talks to |
|-----------|--------|----------------|----------|
| `app/pack.py` (Pydantic models + `load_pack(slug)` + cache) | NEW | Validate and expose pack YAML; fail fast on bad pack | policy, agent, tools, faq, engine modules, `make new-business` |
| `businesses/<slug>/*.yaml` | NEW (summit-roofing seeded from code) | Data | pack.py |
| `app/tenants.py` (resolve tenant from key/channel/default) | NEW | Request -> tenant_id, pack | main.py, admin.py, deps |
| `policy.py` | MODIFIED | Keep generic: escalation core, `unsupported_claim`, `answer_supported`, `pick_slot`, `looks_like_question`, `not_ready_grounded`, `MAX_FAILED_TURNS`. Move out: SERVICE_AREA, QUALIFYING_SERVICES, MAX_TIMELINE, ASK, SAFE_FALLBACK text, `_SERVICE`, `_NON_ROOF`, own/timing regexes | pack |
| `qualify.py` (rule interpreter: in_list, yes_no, max_number, in_area; `status`, `missing`, `is_grounded` per rule) | NEW | Replaces `qualification()`, `missing_fields()`, field-specific branches of `is_grounded` | policy, agent, evals/runner.py |
| `agent.py` | MODIFIED | Replace module constants (`CLOSED_REPLY`, `DISQUALIFY_REPLY`, `NURTURE_REPLY`, `NO_SLOTS_REPLY`, inline "free roof inspection" strings, booking email) with `pack.messages`; load pack; pass tenant to `_open` and tools | pack, tools |
| `tools.py` | MODIFIED | `ensure_slots`, `get_available_slots`, `book_appointment`, `lookup_faq`, `_faq_keywords`: add `tenant_id` param and `calendar` settings | db |
| `faq.py` | MODIFIED | `seed_faq(pack)` per tenant from `knowledge.yaml`; the `if any row exists: return` guard must become per-tenant | pack, llm |
| `schemas.py` | MODIFIED (late) | `ServiceType` enum and `LeadFields` are roofing-specific (repair/replacement/inspection). Pack #2 needs different values. See pitfalls | qualify |
| `triage.py` / `clients/*.yaml` | MODIFIED (small) | `policy.escalation_reason(message)` must take pack escalation config. Fold `clients/*.yaml` into pack `business.yaml` + `triage:` later; keep `clients/` working until then | pack |
| `llm.py` | MODIFIED (step 6) | Add Anthropic provider to chain; `load_prompt` unchanged | prompts |
| `prompts/agent.v2.md`, `faq-answer.v1.md`, `system.v1.md`, `agent.v1.md` | MODIFIED | Hardcode "Summit Roofing", "roof inspections", service_type enum in the JSON schema, the worked example. Template `<<business>>`, `<<offer>>`, `<<service_values>>`, `<<example>>` | agent |
| `engine/quote.py`, `capacity.py`, `review.py`, `brief.py`, `intake_event.py` | NEW | Pure functions of (pack, input) | pack, connectors, agent_events |
| `connectors/` (base adapter, sheet/accounting/bookings/ads/supplier + mocks) | NEW | One adapter per source; mock chosen by `connectors.yaml` | engine, `mcp_server.py` |
| `mcp_server.py` | NEW, separate process | Exposes the same adapters over MCP (stdio or HTTP) | connectors |
| `agent_events` table + `events.emit()` | NEW | Append-only tenant-scoped event log | agent, engine, dashboard |
| `db/` migrations | NEW | See "Migrations" | everything |
| n8n workflows (6 existing) | MODIFIED | Add `tenant_id` to webhook payload and to API calls | admin.py routes |
| n8n workflows (6 new) | NEW | Thin triggers | API routes |

### Data Flow Changes

- Today: no tenant. `_open()` inserts `leads DEFAULT VALUES`; all SQL is global. After step 2: `_open(..., tenant_id)` sets `leads.tenant_id` and `conversations.tenant_id`; every other query already filters by `conversation_id`/`lead_id` so they inherit tenant through the join. Only slots, faq_chunks and "list" queries in `admin.py` need a direct `tenant_id` filter.
- Pack is loaded once per request (cached by slug + file mtime or fixed at startup). `handle_turn` gets `pack` (or looks it up from `conversations.tenant_id`) so a conversation always uses the pack it started under.
- Booking emails: `_notify_booking` pulls owner email, name, offer, demo disclaimer from the pack. `settings.owner_email` becomes the fallback only.

## What the spec missed (unread files: `intake.py`, `prompts/`, plus other hits)

| Location | Finding | Impact |
|----------|---------|--------|
| `intake.py` | **Not roofing.** It is RoofDesk's own sales-chat (`PROFILE = "roofdesk-ai"`, fixed STEPS name/business/email/phone/need, saves a `pilot` request). It never touches leads/slots/policy except `policy.looks_like_question`. | Do NOT make it tenant-driven. It is the platform's own sales funnel, same category as outbound. Leave alone; only note that `/intake` (this) collides in name with the planned "intake webhook" (waiver/check-in events). Name the new one `intake_event` / `/webhooks/intake-event`. |
| `prompts/agent.v2.md` (live, `PROMPT = "agent.v2"`) | Hardcoded: "Summit Roofing, a roofing company that books free roof inspections", `service_type: repair\|replacement\|inspection\|other`, "free roof inspection" FAQ framing, `timeline_months`, the "Sam ... repair next month" example, `is_owner` field. | HIGH. This is the biggest hidden roofing coupling. The extraction JSON schema itself is roofing-shaped; a dental pack with different fields cannot extract through it. Needs templating AND a per-pack field list (see Pattern 2). Prompt text change can move the 8B model's accuracy, so it is gated by evals. |
| `prompts/faq-answer.v1.md`, `system.v1.md`, `agent.v1.md` | Hardcode "Summit Roofing". `agent.v1`/`system.v1` look unused by live code (agent uses v2). | Template faq-answer.v1 (live). Delete or ignore v1 files; `evals/runner.py` imports `PROMPT` to record version. |
| `agent.py` | Beyond what the spec lists: `_KNOWN_KEYS`, `Turn`/`LeadFields` fixed field set, `_offer_slots` prefix "free roof inspection!", `_notify_booking` body + subject + demo disclaimer, CLOSED_REPLY["DONE"] "Your inspection is booked". `_fmt` uses server timezone (`strftime` on isoformat, no tz conversion). | Timezone from `business.yaml` is needed for slot generation (see below) and for `_fmt`. |
| `policy.py` | `SAFE_FALLBACK` ("free roof inspection"), `_GENERIC` stopword list contains "roof roofing summit inspection(s) estimate" (affects `answer_supported` threshold, so moving it can flip eval cases), `_CLAIM_RE` treats `$`/percent/warranty-years as claims (would block quoted prices from the quote builder: quotes must bypass this check or `unsupported_claim` must accept numbers from the quote result), `is_grounded` own/time/service regexes. | `_GENERIC` split: keep generic words in code, move roofing words to `pack.vocabulary_extra` and union them. Do it verbatim for roofing or the 2 known failures may shift. |
| `tools.py` | `SLOT_HOURS` in server-local tz via `date_trunc('day', now())` (DB tz, likely UTC); `appointments.lead_id UNIQUE` (one appt per lead, global) and `slot_id UNIQUE`; `ensure_slots` NOT EXISTS check is by `start_time` only, so with two tenants the second tenant's slots at the same hour are silently skipped. | Must add `tenant_id` to the NOT EXISTS clause or slots will be missing for tenant 2. This is a silent bug, not an error. |
| `faq.py` `seed_faq` | Returns early if `faq_chunks` has any rows; `faq_seed.sql` is also loaded by `bootstrap.py` on fresh DB. Embedding dim fixed `vector(384)`. | Two seed paths (SQL + Python) must both become tenant-aware or the hosted deploy will seed rows with the wrong/null tenant. |
| `admin.py` | Hardcoded "Your free roof inspection with Summit Roofing" follow-up draft (lines ~187-189); `/metrics`, lists, `followups/due` are global; `/webhooks/inbound` lives in the admin/hook area. | Follow-up cadence and text from pack; all metrics queries need tenant filter or become cross-tenant leaks. |
| `replies.py`, `outreach.py`, `pilot.py` | Mention roofing but as outbound for selling RoofDesk (sample roofing company). | Leave. Out of customer package. |
| `config.py` | `client_profile = "summit-roofing"` global default; `owner_email`, `sender_*` global. | Default tenant slug setting; per-tenant owner in pack. |
| `evals/runner.py` | Imports `policy.qualification` directly (`invalid_booking` check), `load_scenarios()` globs only `evals/scenarios/*.yaml`; 10 categories by file; `channel="eval"` conversations excluded from metrics by `channel <> 'eval'`; `latest.md` vs `latest-partial.md` rule keyed on total scenario count. | Runner must take `--pack`, call `qualify.status(lead, pack)`, load `businesses/<slug>/scenarios/`, write per-pack reports (otherwise running pack #2 overwrites roofing baseline `latest.md`). The `len(results)==len(load_scenarios())` rule needs to be per-pack. |
| `docker-compose.yml` | Mounts `./prompts`, `./clients`, `./db`, `./evals`; no `businesses/` mount; DB init only runs `init.sql` + `outreach.sql` on empty volume (not `faq_seed.sql`, which bootstrap handles). | Add `./businesses:/srv/businesses:ro`; add `settings.businesses_dir`. Migrations on an existing volume will not run from `docker-entrypoint-initdb.d`. See Migrations. |
| `n8n/workflows/*.json` | All use `{{ $env.API_URL }}` and `ADMIN_API_KEY` env; mail goes straight to `http://mailpit:8025/api/v1/send` (not through the API). `from`/recipient addresses are hardcoded in workflow JSON. | "Owner from the pack" means n8n must receive the owner address from the API response, not hardcode; or API sends the mail. See n8n section. |

## Patterns to Follow

### Pattern 1: Pack extraction by golden-copy (behaviour-preserving)
**What:** Step 3 moves constants verbatim into YAML and replaces each constant with `pack.<field>`; no string is reworded.
**When:** Every extraction step. Any rewording is a separate commit with its own eval run.
**Example:**
```python
# pack.py
class Qualification(BaseModel):
    criteria: list[Criterion]
    disqualify_text: str
class Pack(BaseModel):
    business: Business; qualification: Qualification; messages: Messages
    knowledge: list[Fact]; calendar: Calendar; escalation: Escalation
    services: Services | None = None; capacity: Capacity | None = None
    connectors: Connectors = Connectors()
    model_config = ConfigDict(extra="forbid")   # typo in YAML fails at load, not at 3am
```

### Pattern 2: Fields and rules are the pack's, extraction schema derives from them
**What:** The roofing `LeadFields` is not generic. Choose: keep `LeadFields` as the fixed *column* set (name, phone, email, address, service_type, property_type, is_owner, timeline_months, budget_range) and have each criterion's `field` point at one of them (cheapest, matches spec's example). Pack #2 dental reuses `service_type` (cleaning, whitening...), `is_owner` is simply not a criterion. Do NOT add arbitrary fields until pack #3 forces it, then add `leads.custom JSONB`.
**Why:** `update_lead` builds SQL column names from the schema keys; arbitrary fields would break that safety property.
**Consequence:** `ServiceType` enum must become `str` validated against `criterion.values` (+ "other"). Done in step 4, not 3.

### Pattern 3: Old path stays until new path passes (dual-run)
**What:** In step 4, keep `policy.qualification()` and add `qualify.status()`. Add a unit test that runs both over every lead dict seen in eval results/test_policy and asserts equality, then switch call sites. Delete old only after 94/96 holds.
**When:** step 4 specifically. This is a cheaper and tighter gate than the LLM eval because the rule interpreter is pure and deterministic (the 8B model is nondeterministic run to run).

### Pattern 4: Tenant by explicit parameter, RLS last
**What:** Pass `tenant_id` explicitly into tools and SQL (`WHERE tenant_id=:t`). Add RLS in step 8 using `SET LOCAL app.tenant_id` per transaction via a SQLAlchemy `begin` event or a `tenant_conn(tid)` helper replacing direct `engine.begin()`.
**Why:** The code has ~40 raw `engine.begin()/connect()` call sites (agent, tools, admin, outreach). RLS with a pooled engine needs the setting on every transaction; retrofitting that late is mechanical but touches every file. Introduce a single `db.tx(tenant_id)` context manager in step 2 (initially it just yields `engine.begin()`), so step 8 changes one function. The app DB role must not be a superuser/table owner or RLS is bypassed (owner bypasses unless `FORCE ROW LEVEL SECURITY`).

### Pattern 5: Engine modules are pure; I/O at the edges
**What:** `quote.build(pack.services, request) -> Quote(lines, total, missing)`; `capacity.check(pack.capacity, bookings, roster) -> flags`. Route handlers fetch data (via connectors), call pure function, write `agent_events`, return JSON. Model only wraps text around the result, and the existing `unsupported_claim` style check verifies every number in the draft appears in the Quote.
**Why:** Evals stay deterministic and need no LLM (quote/capacity/brief diff against fixtures).

### Pattern 6: Connectors = one interface, two front ends
**What:** `class Connector(Protocol): def fetch(self, query) -> dict`. A real/mock implementation chosen by `connectors.yaml`. REST routes call it in-process; `mcp_server.py` wraps the same objects (official `mcp` Python SDK, FastMCP) as a separate process/compose service. Don't mount MCP inside the main FastAPI app initially: separate container keeps the main API surface and auth unchanged.
**Note:** MCP server auth/tenant: pass tenant as a tool arg or env at server start; local stdio demo is fine.

### Pattern 7: `agent_events` as a thin emit, not a framework
**What:** `events.emit(tenant_id, conversation_id|None, kind, payload)` insert-only. Distinct from existing `events` table (per-conversation, `kind`, `detail`, used by follow-up scheduling: `kind='followup'`) and `tool_calls`/`llm_calls`. Call sites: end of `_decide`, tool `run()`, engine modules. Payload must be pre-masked (no names/emails) for Agent Office; store ids and kinds only. Add it in step 2 migration (table only) and emit lazily afterwards, so it is not on the critical path. Agent Office and Flight Recorder are the only consumers; both are optional.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Big-bang pack + interpreter
**Why bad:** If score drops you cannot tell if the cause is a moved string, a changed regex or model noise.
**Instead:** Step 3 (data move, same logic) and step 4 (logic swap) are separate commits each with a full eval run and diff of `latest.md`.

### Anti-Pattern 2: Treating one 94/96 run as the gate
**Why bad:** Local Llama is nondeterministic; "same two failures" can flake (+/-1). A false alarm at step 3 sends you hunting a non-bug, a false pass hides a regression.
**Instead:** Gate = (a) deterministic suite: `pytest` + a golden test that the pack-derived values equal the old constants, (b) eval compared per scenario id against saved baseline, same 2 failing ids; any other flip gets rerun x2 before being counted as a regression. Save per-scenario results (eval_results table already stores them) and diff by id, not by total.

### Anti-Pattern 3: Making `/intake` (RoofDesk sales chat) tenant-driven
See unread-file findings. It is the product's own funnel.

### Anti-Pattern 4: Running n8n logic with the pack
**Why bad:** violates "platform runs without n8n". Pack reads happen in API; n8n gets an opaque tenant id and API responses that already contain recipient and text.

### Anti-Pattern 5: Quote numbers through the existing claim guard
`_CLAIM_RE` flags any `$`/% not in FAQ text; quote emails would be replaced by SAFE_FALLBACK. Validate quote drafts against the Quote object instead.

## n8n tenant-awareness

- Current shape: workflows call `API_URL` with a single shared `ADMIN_API_KEY` env; mail goes direct to Mailpit with hardcoded addresses. `compose` passes the escalation webhook `ESCALATION_WEBHOOK_URL` to the API, which posts `{conversation_id, reason, link}`.
- Minimum change: (1) webhook paths take `tenant` (query param or body field, default `summit-roofing`) and forward it as `X-Tenant` header or body field to `/webhooks/inbound`; (2) API echoes `owner_email`, `signature` in responses/escalation payload so n8n does not hardcode them; (3) schedulers (followup, daily-brief, capacity nightly) need a "for each tenant" first node: `GET /admin/tenants` then SplitInBatches. That endpoint is new. (4) Daily-brief fires at tenant local time: either one cron per hour with API filtering tenants whose local hour matches, or the API exposes `/admin/tenants/due-brief`. The hourly-cron variant keeps n8n dumb.
- Workflow JSON is imported on every start via `import:workflow` from `n8n/workflows/` (compose command): editing JSON in repo is the deploy path; do not edit in the n8n UI. IDs equal file basenames for `publish:workflow`; new workflows must follow that.
- Per-tenant keys (step 8): the n8n `$env.ADMIN_API_KEY` model works only for admin; tenant-key auth should apply to `/chat` and webhooks, admin stays one key. Keep that split to avoid storing N keys in n8n.

## Migrations

`db/init.sql` runs only on an empty volume, and `bootstrap.py` only when `leads` does not exist. Existing DBs (local dev with data, the live demo) get nothing. Add `db/migrations/NNN_*.sql` applied by a tiny runner in `bootstrap_schema()` tracked in a `schema_migrations` table (no Alembic; the project uses raw SQL and this is the simplest thing). Also keep `init.sql` equal to final schema for fresh installs, or make fresh installs run init then all migrations (simpler, single source of truth for new columns).

Step 2 migration: `tenants(id, slug unique, name, created_at)`, insert Summit Roofing as id 1; `ALTER TABLE ... ADD COLUMN tenant_id INT NOT NULL DEFAULT 1 REFERENCES tenants(id)` on `leads, conversations, slots, faq_chunks` (plus `appointments` is reachable via slot/lead; `escalations`, `messages`, `tool_calls`, `llm_calls`, `events` reach tenant via conversation, add a column only when RLS lands). Constant DEFAULT 1 is cheap on PG16 (no rewrite). Do NOT add a default in step 8; drop the DEFAULT so a missed code path errors instead of silently writing to Summit. Also: `slots` unique(tenant_id, start_time); `faq_chunks` index on tenant_id; `external_id UNIQUE` on conversations must become unique per tenant `(tenant_id, external_id)` (an SMS number could talk to two businesses). `outreach.sql` tables (prospects, campaigns, outreach messages): leave untenanted; they belong to the RoofDesk operator, not customers. Remember `eval` channel conversations are tenant 1 unless runner sets the pack's tenant.

## Suggested Build Order (with dependencies and gates)

Gate for every step: `make test` + `make eval` + per-scenario-id diff vs `v1-roofing` baseline; live demo untouched (branch; deploy only on request).

1. **Baseline freeze**: tag `v1-roofing`; copy `evals/reports/latest.md` and dump `eval_results` per scenario id to `evals/reports/baseline-v1.json`. Run eval 3x to measure flake rate; that sets the real tolerance. (Untracked `latest-partial.md` in git status is a partial run; do not treat as baseline.)
2. **Tenants + migration runner + `db.tx()` + `agent_events` table + `tenant_id` threading** (default tenant 1, resolver returns default). Fix `ensure_slots` NOT EXISTS and `faq` seed guard now, since they are only wrong once a second tenant exists, but make them tenant-aware at this step while behaviour is unchanged. Depends on: 1. Risk: low.
3a. **Pack loader + Pydantic models + summit-roofing YAML** with a golden test asserting pack values == old constants (SERVICE_AREA, ASK text, FAQ list, SLOT_HOURS, messages). No call sites changed yet. Depends on: 2.
3b. **Rewire call sites to the pack** (agent messages, tools calendar, faq seed from pack, prompts templated with `<<business>>`/`<<offer>>`; rendered prompt for roofing must be byte-identical to current text; assert in a test). Gate: 94/96. Prompt byte-identity test is the cheapest regression catcher for the model-sensitive part.
4. **Rule interpreter** `qualify.py` with dual-run equivalence test over a lead-dict corpus (grid of service/owner/address/timeline values incl. edge addresses like "5 Elm St Apt 4, Denver CO 80202"); then switch `policy.qualification/missing_fields/next_question/is_grounded` and `evals/runner.py`'s `policy.qualification` use; synonyms/regex to pack. Then relax `ServiceType` enum. Gate: 94/96 + dual-run test. Hardest address logic (`address_status`) becomes the `in_area` rule: port it unchanged, with city list from pack. `in_area` for non-address-based businesses (dental: maybe no area) = criterion simply absent.
5. **Eval runner per pack** (`--pack`, per-pack report files, scorecard by category) BEFORE writing pack #2. Then pack #2 dental + ~40 scenarios. Existing `clients/bright-smile-dental.yaml` already holds triage facts, reuse as seed for `business.yaml`/`knowledge.yaml`. Depends on: 4 (interpreter) and the prompt templating (3b). Expect to need: per-pack extraction example in prompt, dental service values, escalation extras (e.g. dental emergency/pain in `always_human`), and `unsupported_claim` interplay for prices. Gate: roofing still 94/96; dental no category < 90%.
6. **Engine modules** in this order: quote builder (needs `services.yaml`, touches claim guard), capacity checker (pure, small), connector layer + mocks (prereq for brief), daily brief, review responder (same draft checks as outreach: reuse `replies.py`/outreach draft guards), intake_event, supplier-order (optional, depends on quote add-ons). Each ships with its own deterministic eval set. Anthropic provider (llm.py) is independent: can be done any time after step 1 and is the one change that is safe to parallelise. MCP wrapper after connectors. `agent_events` emits added as each module lands.
7. **n8n tenant-aware**: existing 6 first (tenant param, owner from API, tenants loop), then the new workflows, one per module as each module's API route exists. Cannot precede its API route; do not start before step 6 route exists. Third pack after step 6 (needs capacity, quotes, intake).
8. **Per-tenant keys + RLS**: `api_keys(tenant_id, hash)`, resolver switched from default to key lookup; `db.tx()` sets `app.tenant_id`; policies on every tenanted table; non-owner DB role; remove column DEFAULT 1. Add a cross-tenant leak test (tenant A key cannot read tenant B conversation, FAQ, slots, metrics). This is where `admin.py` global queries are audited. Public multi-tenant exposure only after this.
9. **Docs/PII masking/retention**: PII mask as a logging filter (the code logs via `logging` with ids mostly, so cheap); retention = scheduled delete in API; SOP generator reads pack + workflow catalog. Depends on all workflows existing.
10. **Held-out 20 scenarios** after step 6 and before tuning on them; run once.

Reordering notes against the spec: (a) split step 3 into data-move and rewire, (b) move per-pack eval runner into step 5 start, (c) create `db.tx()` and migration runner in step 2 so step 8 is small, (d) `agent_events` table in step 2 but emits deferred.

## Scalability Considerations

| Concern | 1-3 tenants (this milestone) | 100 tenants | 10K |
|---------|------------------------------|-------------|-----|
| Pack loading | Read YAML at startup + mtime cache | Same, in-process dict | Pack in DB with versioning |
| Slots | `ensure_slots` per request with tenant filter | Nightly job instead of per request | Partition/time-bucketed |
| FAQ vectors | pgvector sequential scan filtered by tenant is fine | ivfflat/hnsw + tenant filter | Per-tenant partitions |
| DB pool/RLS | Pooled engine, `SET LOCAL` per tx | Same | pgbouncer in transaction mode (SET LOCAL works) |
| LLM | Local Ollama single GPU | Hosted provider chain | Out of scope |

## Sources

- Direct code read, repo `ervenderr/roofdeskai` master (files named above): HIGH
- Spec: `RoofDesk Global Platform Spec.md` (Nov 3, 2026)
- PostgreSQL row security docs (owner bypass, `FORCE ROW LEVEL SECURITY`, `SET LOCAL` pattern) from prior knowledge, not re-verified this session: MEDIUM
- MCP Python SDK (FastMCP) approach from prior knowledge, not re-verified: MEDIUM; check the SDK's current API before step 6
