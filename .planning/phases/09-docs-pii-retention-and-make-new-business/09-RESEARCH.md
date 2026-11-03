# Phase 9: Docs, PII/Retention and make new-business - Research

**Researched:** 2026-11-04
**Domain:** ops tooling on an existing FastAPI/Postgres(RLS)/n8n stack. No new libraries.
**Confidence:** HIGH (all from code in this repo; nothing external needed)

<user_constraints>
## User Constraints (from CONTEXT.md)
Locked: D-01..D-09 (see 09-CONTEXT.md; unchanged). Discretion: module names, regexes, table classification, CLI shape, plan split (~6), no n8n retention workflow.
Deferred (out of scope): GitHub Actions, legal review of health data, automated key minting, n8n retention workflow.
Roofing and dental pack files and prompts stay byte-identical.
</user_constraints>

<phase_requirements>
| ID | Research support |
|----|------------------|
| OPS-01 | s3 (runner/in-process smoke), s2.1 (tenant registration) |
| OPS-02 | s6 gen_docs |
| OPS-03 | s2 mask + filter install, UUID/phone pitfall |
| OPS-04 | s1 table map, delete order, grants gap (migration 008) |
| OPS-05 | s1 table list feeds data-map + test |
| OPS-06 | s4 hit list and allowlist |
| OPS-07 | s5 README markers |
</phase_requirements>

## Summary
No new dependencies. Everything is stdlib + existing SQLAlchemy/pytest. Biggest findings that change plans:
1. The raw gate `roof|summit|denver` matches the product name "RoofDesk" everywhere (~40 hits). Use `roof(?!desk)|summit|denver` (PCRE-style, Python `re` supports the lookahead), after stripping the token `America/Denver`. That leaves 5 real shared-code buckets (s4).
2. `app_rw` has no DELETE on `drafts`, `capacity_flags`, `brief_runs`, `agent_events` (005/007 grants), and `agent_events` has an UPDATE/DELETE/TRUNCATE-blocking trigger. Purge in tenant context therefore needs migration `008` (GRANT DELETE on those three; `intake_people` already has DELETE). `agent_events` should be kept-with-reason (see s1).
3. `evals.runner` plain mode never exits non-zero on scenario failure (only `--gate` does, vs a baseline a new pack lacks). `make new-business` must call runner functions in-process, not shell out.
4. There is no "cross-tenant" scenario category in eval YAML. Cross-tenant retrieval is covered by pytest (`test_isolation.py`). The smoke script must do its own deterministic cross-tenant check (s3).
5. uvicorn installs its own handlers on `uvicorn`/`uvicorn.access`; a filter on root handlers alone misses access logs (s2).

**Primary recommendation:** 6 plans, three waves (s8). Keep every new module small and pure; put the table classification in ONE dict (`retention.py`) that retention, delete_subject, the coverage test and the data-map test all read.

## Architectural Responsibility Map
| Capability | Tier | Rationale |
|---|---|---|
| PII mask / log filter | API process (logging) | Stdlib filter on handlers |
| Retention purge, delete_subject | API/DB (tenant tx, RLS) | Decisions in FastAPI; n8n not involved (D-04) |
| make new-business | Script in api container | Needs DB + LLM; runs in g-* stack |
| SOP/runbook/README generation | Dev-time script + pytest drift | Reads pack YAML + n8n JSON; no runtime tier |
| Grep gate | pytest + make | Static file scan |

## Standard Stack
No additions. Use: `re`, `logging`, `hashlib`, `string.Template`, `pathlib`, `json`, `yaml` (pyyaml, existing), `sqlalchemy` text via `db.tx` / `db.system`. Jinja2 NOT needed (D-06): SOPs are per-workflow lists of fixed fields; loops done in Python and joined into a single `$body` substitution.

## Package Legitimacy Audit
No external packages installed this phase. Nothing to audit.

## 1. Tables, PII, retention, delete order (OPS-04, OPS-05)

Tables with `tenant_id` (migrations 001-007; verified in db/migrations): `leads, conversations, messages, slots, appointments, faq_chunks, tool_calls, escalations, events, llm_calls (tenant_id nullable col, backfilled in 002), agent_events, drafts, capacity_flags, brief_runs, intake_people`. Also `tenants` (is the tenant row; no tenant_id) and `tenant_api_keys` (has tenant_id, NO RLS, no app_rw grant, system ctx only). Outreach tables (prospects, campaigns, outreach_messages, suppressions, ...) have no tenant_id: RoofDesk-own, out of scope but list them in the data-map.

| Table | PII? | Retention timestamp | Action |
|---|---|---|---|
| leads | name, phone, email, address | `created_at` | purge via parent chain (below) |
| conversations | `external_id` (SMS contact id), lead link | `started_at` | purge |
| messages | free text from the person | `created_at` | purge |
| tool_calls | `args_json`/`result_json` (contain name/email) | `created_at` | purge |
| escalations | `reason` (may echo text) | `created_at` | purge |
| events | `detail` text | `created_at` | purge |
| llm_calls | no PII (model, tokens); FK to conversation | none (no created_at) | delete with its conversation |
| appointments | lead link, status | `created_at` | purge when lead purged (past appointments only; keep future ones) |
| drafts | `payload` has contact_email / review text (quote, review_reply) | `created_at` | purge (needs DELETE grant) |
| intake_people | `name`, `person_key`, waiver/check-in/result | `created_at` (also `updated_at`) | purge; DELETE already granted |
| capacity_flags | shift ids/dates/details, no person | `first_flagged_at` | purge (config-like ops data; grant needed) or kept-with-reason. Recommend purge by `first_flagged_at`. |
| brief_runs | aggregate `payload`; may include lead names | `created_at` | purge (grant needed) |
| agent_events | contract: ids/names/flags only, NO PII (`db.record_event` docstring). Append-only trigger. | `created_at` | KEEP, reason "audit trail, no PII by contract; append-only trigger". Resolves D-04's "agent_events PII fields" ambiguity (Open Q1). |
| slots, faq_chunks | config | - | KEEP (config) |
| tenant_api_keys | key hash | - | KEEP (credentials, not subject data) |

**Cutoff semantics:** keep it per-conversation, not per-row, so FKs hold: select conversations with `started_at < cutoff`, delete their children, then conversations, then orphaned leads. Leads purge rule: lead has `created_at < cutoff` AND no remaining conversation referencing it (after deleting old conversations) AND no future appointment.

**FK graph (composite `(tenant_id, id)`):** `messages, tool_calls, escalations, events, llm_calls -> conversations(tenant_id,id)`; `conversations.lead_id -> leads`; `appointments.lead_id -> leads`, `appointments.slot_id -> slots`. `agent_events.conversation_id` has no FK (by design).

**Delete order (both purge and delete_subject):**
1. `tool_calls, events, escalations, llm_calls, messages` WHERE `conversation_id = ANY(:cids)`
2. `UPDATE slots SET is_booked=false` for slots of the doomed appointments (otherwise capacity leaks), then `appointments` WHERE `lead_id = ANY(:lids)`
3. `conversations` WHERE id = ANY(:cids)
4. `leads` WHERE id = ANY(:lids)
5. `drafts, intake_people, capacity_flags, brief_runs` (independent, by time or by subject match)
Every statement includes `tenant_id = :t` even though RLS enforces it (belt and braces; admin ctx would not).

**delete_subject linkage:** identifier `email|phone|external_id` -> `leads` by `lower(email)=lower(:v)` or normalized phone (digits only compare; strip non-digits on both sides in SQL with `regexp_replace`), -> conversations by `lead_id` OR `external_id = :v` (an SMS contact has a conversation via `external_id` and may have no lead row yet) -> children. Also `intake_people.person_key = :v` (person_key may be an email or id; exact match, case-insensitive) and `drafts` where `payload->>'contact_email'` matches (inspect exact payload keys in `quotes.py`/`reviews_routes.py` during implementation; LOW: not read here). Return `{store: count}`.

**Audit row:** write to `agent_events` via `db.record_event(c, t, None, "subject_deleted", {"id_hash": sha256(identifier.lower()).hexdigest()[:16], "counts": {...}})`. app_rw has INSERT on it; no new table, no migration for this. Truncate the hash is fine; never store the identifier.

**Migration 008 (final once applied, no checksum):** `GRANT DELETE ON drafts, capacity_flags, brief_runs TO app_rw;` only. Use `-- FINAL` header like 007. Do not touch agent_events trigger.

**Admin endpoint:** `POST /admin/retention/run` super-admin only. Existing admin routes use `require_scope`; `tenant_admin.py` router (`/admin/tenants`) is the super-admin-only pattern (no tenant scope) so put retention + delete_subject-by-admin there, tenant-scoped `delete_subject` in a tenant route (`tenant_routes.py`, `/tenant/subject/delete`, POST, body identifier). Admin variant takes explicit tenant id (admin endpoints have no implicit tenant: `tx(None)` raises on purpose). Purge loops `SELECT id FROM tenants` under `system()`, then `tx(tid)` per tenant. `RETENTION_DAYS` goes in `config.py` Settings (`retention_days: int = 0`; 0 = no-op, returns empty counts).

**Coverage test (D-05):** copy the `assert_rls_enforced` query shape (pg_attribute `tenant_id`, relkind 'r') to list tables, assert each is in `RETENTION_MAP` (purged) or `KEPT` (with reason string). The same list drives the data-map test (each table name appears in docs/data-map.md). `tenants` itself has no `tenant_id` column so is not listed; mention it in the map by hand.

**Test cleanup interactions (conftest `remove_test_data`):** it only deletes tenants with slug `test-%` (plus `demo-venue`), and lifts the agent_events trigger inside its own transaction to delete fixture-tenant events. New purge/delete tests MUST create tenants named `test-...` (via the existing tenant fixtures in test_tenancy/test_isolation) so cleanup removes their `subject_deleted` audit events. Never run purge tests with `RETENTION_DAYS` leaking into other tests: pass days as an argument to the function, don't mutate settings globally (monkeypatch if endpoint test). Purge function must take `tenant_id` + `days` params; the endpoint reads settings. Never run purge across all tenants in a test (it would delete dev DB roofing/dental conversations): test only the per-tenant function against a test tenant, and test the endpoint with a monkeypatched tenant list or `tenant` param.

## 2. PII mask and logging (OPS-03)

Present: `api/app/engine/pii.py` has `EMAIL_RE = [\w.+-]+@[\w-]+(?:\.[\w-]+)+`, `PHONE_RE = \+?\d[\d\s().-]{7,}\d`, `ADDRESS_RE`. `api/app/logctx.py` has `current_tenant` ContextVar + `TenantFilter` (sets `record.tenant_id`, returns True). `main.py` lines 35-37: `logging.basicConfig(level=INFO, format="... tenant=%(tenant_id)s %(message)s")` then `for _h in logging.getLogger().handlers: _h.addFilter(TenantFilter())`. Existing test: `api/app/test_logging_tenant.py` (use as the pattern).

**Pitfall (verified by reading the regex): `PHONE_RE` also matches tenant UUIDs** (`00000000-0000-0000-0000-000000000001` is digits and dashes, 36 chars) and date-times like `2026-11-04 12`. Logs contain tenant UUIDs (e.g. `faq seed failed for tenant %s`). Using `PHONE_RE` as-is would mangle them and defeat the `tenant=` field's usefulness in message text. Fix in `mask()`: one alternation regex, UUID first, replaced by itself via a callback:
`_TOKEN = re.compile(rf"(?P<uuid>{UUID})|(?P<email>{EMAIL_RE.pattern})|(?P<phone>(?<![\w-])\+?\(?\d[\d\s().-]{{6,}}\d(?![\w-]))")` and the callback returns uuid unchanged; for phone require 8-15 digits after stripping non-digits, else unchanged (protects dates/ids/counts). Do NOT add the address regex to log masking (D-03 says email and phone only; ADDRESS_RE stays for review check).

**Spec details:** `mask(text) -> str`; non-str input -> `str()` first; never raises (wrap in try/except returning `"[unmasked-failed]"`); idempotent on already-masked (`[email]`, `[phone]` contain no digits/@). Unit cases: two emails in one string, `a.b+c@x.co.uk`, near-miss `user@` and `@handle`, `12345` and `1234567` (short), ISO date, UUID, Swiss `+41 44 123 45 67`, US `(303) 555-0142`, unicode name next to an email, already-masked.

**Filter:** `class PiiMaskFilter(logging.Filter)` in `logctx.py` next to `TenantFilter`. In `filter()`: `record.msg = mask(record.getMessage()); record.args = None` (formatting args first is the only way to mask `%s` args reliably; wrap in try so a bad format string falls back to masking `str(record.msg)`). Also mask `record.exc_text`: if `record.exc_info` and not `exc_text`, set `exc_text = logging.Formatter().formatException(record.exc_info)` then mask it (tracebacks echo values). Always return True.

**Install points:** (a) `main.py` loop at line 36: add `PiiMaskFilter()` beside `TenantFilter()`. (b) uvicorn: `--reload` CMD in `api/Dockerfile`; uvicorn configures `uvicorn` and `uvicorn.access` loggers with their own handlers and `propagate` False for access, so root-handler filters do not see access-log lines (which contain URL query strings, possibly emails). Also add the filter to handlers of loggers `uvicorn`, `uvicorn.error`, `uvicorn.access` in the same loop (`for name in ("uvicorn","uvicorn.error","uvicorn.access"): for h in logging.getLogger(name).handlers: h.addFilter(...)`). `main.py` is imported by uvicorn after its logging config, so those handlers exist. Test: attach filter to a capturing handler on a fresh logger and assert output; plus one test asserting `main` installed it (inspect `logging.getLogger().handlers[*].filters` after import, same style as test_logging_tenant).
Limitation to document in data-map: n8n execution data and Mailpit are NOT covered by this filter.

## 3. Eval runner, scenario selection, registration, stack (OPS-01)

`evals/runner.py`: `--pack <slug>` (default `summit-roofing`), `--ids a,b`, `--category x`, mutually exclusive `--write-baseline | --flake | --gate`. `main()` order: `load_pack(slug)` (PackError) -> `t = ensure_tenant(slug)` -> `ensure_slots(t)` -> `sync_faq(t)` -> `load_scenarios(slug)` -> filter -> mode. Plain mode: `run_suite(scenarios, t)` -> `assert_local_only(cids, t)` -> `write_report` (writes `evals/reports/<slug>[-partial].md`; this is why git status shows dirty partial reports). **Plain mode does not exit non-zero on failed scenarios.** Scenario results are `(sc, ?, failed_checks)` tuples; failure = non-empty `failed_checks` (see `baseline_from_results`: `passed: not f`). `CATEGORIES = {voice, qualified, faq, disqualified, vague, out_of_knowledge, injection, out_of_order, escalation, slots}`; `load_scenarios` `sys.exit`s on malformed YAML.

**Scenario ids (verified in YAML):**
- roofing escalation: `esc-angry, esc-legal, esc-human, esc-safety, esc-manager, esc-injury, esc-sue, esc-scam`; injection: `inj-free, inj-admin, inj-leak, inj-dan, inj-price, inj-json, inj-slot, inj-discount`.
- dental escalation: `desc-pain, desc-swelling, desc-knocked-out, desc-bleeding, desc-breathing, desc-meds, desc-after-booking, desc-human`; injection: `dinj-free, dinj-other-business, dinj-leak, dinj-diagnosis`.
- No scenario is tagged cross-tenant. `dinj-other-business` is a prompt-level "ask about another business" injection; the retrieval isolation proofs are pytest (`test_isolation.py::test_lookup_faq_never_crosses`, `test_keyword_fallback_never_crosses`, `test_leak.py`).

**Smoke design (data-driven, D-02):** `scripts/new_business.py`, run in-process:
1. `load_pack(slug)`; on `PackError` print text, exit 1.
2. `t = ensure_tenant(slug); ensure_slots(t); sync_faq(t)` (same calls as runner `main`; idempotent).
3. `scs = [s for s in load_scenarios(slug) if s["category"] in {"escalation","injection"}]`; if no escalation scenario: exit "pack has no escalation scenarios"; if no injection: same style error.
4. `results, cids = run_suite(scs, t)`; `assert_local_only(cids, t)`; every result must have empty failed checks, else print ids and exit 1. Do not call `write_report` (keeps repo clean). Zero tolerance is right for these two categories (baselines: roofing 8/8 and 8/8, dental 8/8 and 4/4); flaky reruns are not needed for a smoke check but allow `--rerun`-free single pass; if flakiness appears, rerun only failing ids once (reuse `RERUNS`).
5. Deterministic cross-tenant check (no LLM): for every other tenant in `tenants` that has a pack: `tools.lookup_faq(<text of other tenant's chunk>, k=50, tenant_id=t)["chunks"]` is a subset of own pack FAQ texts; and under `tx(t)` `SELECT count(*) FROM leads WHERE tenant_id <> :t` is 0 (RLS). Pattern is copied from `test_isolation.py`.
6. Print the reminder: "Every tenant needs a key in TENANT_API_KEYS (POST /admin/tenants/{id}/keys). Without one the n8n loop aborts at Check key." (Phase 8 note) plus the tenant id. Never mint.

**Registration:** `tenants.ensure_tenant(pack_slug)` inserts `tenants(slug, name, timezone, pack_slug)` ON CONFLICT DO NOTHING, raises `PackError` if the slug is bound to another pack; `sync_faq(t)` reseeds only when DB FAQ texts differ. `main.py` lifespan `seed_faq` for all tenants at start. `POST /admin/tenants` (`tenant_admin.create_tenant`) is the HTTP route to the same. Uses `system()` so safe on the owner engine.

**Running in the g-* stack:** Makefile pattern `$(GCOMPOSE) exec -T api python -m scripts.run_flows`. Add:
```
new-business:
	@test -n "$(PACK)" || (echo "usage: make new-business PACK=<slug>"; exit 2)
	$(GCOMPOSE) exec -T api python -m scripts.new_business $(PACK)
```
Targets must use the g stack only (project `roofdesk-global`), never `docker compose` live default (CONTEXT: never touches live DB). `evals` and `scripts` are importable from the api container working dir (same as `evals.runner`, `scripts.run_flows`). Needs Ollama reachable from the api container (LLM) and branch stack up; the script must fail clearly if LLM unreachable (`assert_local_only` already guards hosted fallback). Not run in this research.

## 4. Grep gate hit list (OPS-06)

Command run: `grep -rniE 'roof|summit|denver'` over api/app (non-test), n8n/workflows, prompts, scripts, evals runner code, dashboard code. Raw pattern is dominated by the product name RoofDesk. **Recommended gate regex:** `roof(?!desk)|summit|denver` case-insensitive, after removing `America/Denver` (and per-file allowlist). Real hit list with that regex (excluding test files, conftest, tests_data, snapshot.json):

| File | Hits | Nature | Proposal |
|---|---|---|---|
| api/app/config.py | 2 | `default_tenant_id` comment "Summit Roofing"; `client_profile: str = "summit-roofing"` | Allowlist: legacy default used by triage/admin fallback. Changing default is behaviour change. |
| api/app/triage.py | 1 | comment "roofing safety regex" | FIX: reword comment ("default client's pack"). Zero risk. |
| api/app/engine/reviews.py | 1 | comment "so roofing/dental cannot change" | FIX: reword ("so packs cannot change"). |
| api/app/replies.py | 1 | "sample roofing company" in RoofDesk-own outbound reply | Allowlist: RoofDesk-own outbound module (demo sample company text). |
| api/app/outreach.py | 1 | docstring example "Acme Roofs - Austin" | Allowlist (outbound) or reword to "Acme Co". Prefer reword if no test pins it. |
| api/app/prospects.py | 1 | `TARGET_CATEGORIES` includes "roof" | Allowlist: outbound prospect targeting is a RoofDesk-own business list, not a tenant. |
| prompts/agent.v1.md | 1 | "Summit Roofing, a roofing company that books free roof inspections" | Allowlist: frozen legacy prompt (byte-identical constraint, used by frozen baselines). |
| prompts/system.v1.md | 1 | same | Allowlist: frozen legacy prompt. |
| prompts/agent.v2.md | 2 | few-shot example "5 Elm St, Denver" | Allowlist: editing changes rendered prompt, breaks byte-identical test. |
| n8n/workflows/outreach-flow.json | 4 | `no-reply@summitroofing.test`, `owner@summitroofing.test` | Allowlist: untenanted RoofDesk-own outreach workflow (README: stays on admin key). Do not edit JSON (workflow tests pin structure). |
| evals/runner.py | 14 | `ROOFING = "summit-roofing"` baseline-file naming (`v1-roofing.json`) | Allowlist: frozen regression-gate naming/default pack; reason documented. |
| scripts/seed_demo.py | 10 | roofing demo conversations | Allowlist: demo-data seeder for the live roofing demo. |
| scripts/sample_prospects.json | 3 | sample outreach prospect | Allowlist (outbound sample data). |
| scripts/check-and-deploy.sh | 0 under strict regex (matches only `roofdeskai.com`) | - | none |
| dashboard/app/page.tsx | 1 | "Summit Roofing (fictional)" | Allowlist: demo dashboard page showing the roofing snapshot (or FIX later via tenant name; out of scope). |
| evals/modules/capacity/cases.yaml | 4 | `America/Denver` tz | handled by token strip |
| dashboard/data/snapshot.json | 107 | synthetic data snapshot | Exclude as data |
| Makefile / docker-compose*.yml | 0 strict (match only `roofdesk-global` project name) | - | not scanned or covered by roofdesk strip |

Totals: strict regex = 7 code files with 1-2 hits that are FIX-or-allowlist plus 6 allowlisted buckets. So at most 2 trivial FIXes (comments); everything else allowlisted per file with a one-line reason in a dict `ALLOW = {path: reason}` (per file, not per line, so line drift never breaks the gate; fail if an allowlisted file no longer has hits, so stale entries are removed). Excluded dirs with stated reasons: `businesses/`, `clients/`, `api/app/tests_data`, `test_*.py`, `conftest.py`, `docs/`, `.planning/`, `evals/baselines`, `evals/reports`, `dashboard/data`, `node_modules`, `.next`, `__pycache__`, `scripts/sample_prospects.json`.

Implementation: `scripts/check_shared.py` with `find_hits(root) -> dict[path, int]` (pathlib walk, text suffixes only, skip binary, skip excluded) and `main()` that exits 1 listing offenders; pytest `test_shared_gate.py` imports `find_hits` (no subprocess), also a test that the gate catches a planted hit in tmp_path and that every ALLOW entry still has a hit. `make check-shared: python -m scripts.check_shared` (host or container; pure stdlib, so run host-side `python3 -m scripts.check_shared` works without docker; recommend running directly, no exec). Scanned set should be explicit roots, not repo-wide: `api/app, n8n/workflows, prompts, scripts, evals (runner.py, outreach_runner.py, modules), dashboard/app, dashboard/components, dashboard/lib`. The gate script itself contains the pattern: avoid the literal words by building it (`"ro" + "of(?!desk)"`) or put script under allowlist; simplest: exclude `scripts/check_shared.py` and its test by name with reason.

## 5. README and docs (OPS-07)

README.md (219 lines) headings: `# RoofDesk AI`, What it looks like, `## Scorecard` (line 26; hand-written roofing 94/96 text, metrics table, category table), Architecture, `### n8n flow` (line 61; hand-written catalog with Phase 8 wording "5 new tenant-aware module workflows arriving in later plans" now stale), Outbound, Message triage, Voice, How I check the output, Failures, Run it, Limitations.
docs/: `architecture.html` + 4 `architecture.*.json`, `deploy.md`, `failure-analysis.md`, `img/`, `media/`. No `docs/generated/` yet. No `.github/`.

**Markers:** `<!-- BEGIN GENERATED: scorecard -->` ... `<!-- END GENERATED: scorecard -->` and `catalog`. Put the generated scorecard (per business table: pack, pass/total, per-category, source report) as a new subsection directly under the existing `## Scorecard` text (keep the hand-written roofing narrative: it is claim text about 94/96 and must stay); put the generated workflow catalog inside `### n8n flow`, replacing the stale "Catalog: 3 tenant-aware workflows ..." sentence only. Nothing hand-written lies inside markers.

**Scorecard inputs (committed, deterministic):** per pack JSON in `evals/baselines/` is the machine-readable source: `v1-roofing.json` (roofing; `meta.total/passed`, `scenarios[id].category/passed`) and `bright-smile-dental.json`. Prefer baselines over `evals/reports/*.md` (markdown is unstructured; reports `latest*.md` and `*-partial.md` are uncommitted, dirty working-tree files and must never be inputs). Counts per category computed from the baseline JSON. Module eval counts: count cases per `evals/modules/<module>/cases.yaml` (`brief, capacity, intake, quote, reviews`) by loading yaml (look at `evals/modules/loader.py` for the case shape); report "N cases" only, not pass/fail, since pass requires running evals (not done here). State which commit/date from `meta`.

**Catalog inputs:** `n8n/workflows/*.json` (10 files: capacity-check, daily-brief, error-handler, escalation-alert, followup-scheduler, inbound-message, intake-event, outreach-flow, quote-request, review-reply). Per workflow: `name`, trigger node types (`n8n-nodes-base.webhook` path, `scheduleTrigger`, `manualTrigger`, `executeWorkflowTrigger`), count of nodes, and whether HTTP nodes carry `X-API-Key` (tenant-aware) vs `X-Admin-Key`. Look at `api/app/test_n8n_workflows.py` for the existing helpers and reuse the same parsing logic (import rather than duplicate if cheap).

## 6. Deterministic doc generation (OPS-02, D-06)

`scripts/gen_docs.py`: `render_all(out_root: Path) -> dict[relpath, str]` pure function returning `{path: content}`; `main()` writes (`make gen-docs`); drift test calls `render_all()` and compares each to the committed file, and asserts no extra files under `docs/generated/`. No subprocess, no temp dirs needed (CONTEXT says regenerate to a temp dir; the pure dict is equivalent and simpler: write to tmp_path only for the "main writes files" test).
Determinism rules: `sorted()` on every dict/glob; `json.load` (insertion order is file order, deterministic) but sort anyway; no timestamps, no git sha, no absolute paths; `\n` newlines, single trailing newline; `read_text(encoding="utf-8")`; `yaml.safe_load`; avoid `set` iteration; Decimal/float formatting via explicit f-string formats.
Layout: `docs/generated/<pack>/sop-<workflow>.md` (one per workflow per pack, with pack values substituted: business name, owner role, escalation categories from `escalation.yaml`, hours/timezone from `calendar.yaml`, `messages.yaml` subjects) and `docs/generated/<pack>/runbook.md` (pack + services + keys + retention + who to call; reads `load_pack(slug)` for meta). Use `string.Template` with `$name` placeholders and `safe_substitute` NO: use `substitute` so a missing key raises. Templates stored as Python module-level strings in `gen_docs.py` or `docs/templates/*.tpl`; prefer `scripts/doc_templates/*.md.tpl` read with pathlib (scripts dir is scanned by the gate: templates must not contain the banned words, they are generic).
Use `load_pack(slug)` (typed, validated) for pack data, not raw YAML. Pack attribute names: read `api/app/pack.py` classes (`Pack.meta`, `.calendar`, `.qualification`, `.escalation`, `.messages`, `.faq`) while planning.
Loop over `sorted(p.name for p in businesses_dir.iterdir() if (p/"pack.yaml").exists())` so a new pack gets docs automatically and the drift test forces `make gen-docs` after `make new-business`. Consider having `new_business.py` print "run make gen-docs" (do not auto-run).
Runs host-side or in container; needs pyyaml + pydantic (container has them). Makefile: `gen-docs: $(GCOMPOSE) exec -T api python -m scripts.gen_docs`. The drift test lives in `api/app/` pytest so it runs under `make g-test`. Check that the api container can see `n8n/workflows`, `docs/`, `README.md` and `evals/baselines` (compose volume mounts; `test_n8n_workflows.py` already reads n8n JSON in-container, so n8n is visible; verify `docs/` and README mount at plan time, else fall back to host-side `python3 -m scripts.gen_docs`).

## 7. Risks

- **Byte-identical packs/prompts:** do not edit `businesses/*`, `prompts/*`. `pack_hash(root)` (sha256 over pack files, `pack.py:485`) keys `_CACHE`; any pack edit changes hash and breaks golden/hash tests (`test_pack.py::test_pack_hash_ignores_scenarios` shows scenarios are excluded from the hash). Generated docs go outside `businesses/`. Phase 9 never needs to touch them.
- **Scenario dirs ignored by hash**, so adding a smoke-only scenario to a pack would be allowed but is NOT needed.
- **RLS/admin:** tenant code must use `db.tx(tenant_id)`; `tx(None)` raises. Purge across tenants = `system()` to list tenant ids, then `tx(tid)` each. Do not purge via `system()` DELETEs (bypasses RLS). `assert_rls_enforced` runs at startup; it requires FORCE RLS on all granted tables; 008 adds only a GRANT so it stays green.
- **Migrations final once applied** (`apply_migrations` has no checksum): 008 is GRANT-only, idempotent (GRANT is repeatable). If anything else is discovered, add 009; never edit 001-007. `test_migrations.py` may pin the list/count of migrations: check before adding 008.
- **conftest cleanup:** see s1. Also `remove_test_data` deletes by `conversations.id > first_id` (all conversations created in the session), so a delete_subject/purge test that makes conversations in a non-test tenant gets cleaned anyway but tests must still use `test-*` tenants for tenant-row cleanup.
- **agent_events trigger:** any test that wants to count the audit row reads it (SELECT allowed); cleanup handles deletion.
- **Pinned hashes in generated docs:** do not embed pack hash in docs unless intended (it would change whenever the pack changes; that is acceptable drift but noisy). Recommend omit.
- **make new-business is LLM-bound and slow (~20 scenarios, minutes) and needs Ollama**: pytest must only unit-test its pure pieces (selection, error on missing escalation, result evaluation) with fake `run_suite`; no test should execute the real smoke. Do NOT run evals in plan verification beyond the user's own manual run.
- **Gate vs generated docs:** `docs/` excluded from gate, so generated per-pack docs may name the pack's own words.
- **Dental data caveat:** keep "synthetic demo only; legal review pending (GDPR Art. 9 / nFADP)" wording as "needs review", no legal conclusions.
- **n8n execution data** stores payloads incl. PII and is outside the API purge; document in data-map (no n8n workflow retention, deferred). n8n has `EXECUTIONS_DATA_PRUNE` env settings; mention as a caveat to verify, not claimed (ASSUMED).

## Don't Hand-Roll
| Problem | Use instead |
|---|---|
| Tenant table discovery | copy the `pg_attribute`/`pg_class` query from `db.assert_rls_enforced` |
| Tenant creation / FAQ seed | `tenants.ensure_tenant`, `sync_faq`, `tools.ensure_slots` |
| Scenario loading/running | `evals.runner.load_scenarios`, `run_suite`, `assert_local_only` |
| Audit row | `db.record_event` |
| n8n JSON parsing | helpers in `test_n8n_workflows.py` |
| Docs templating | `string.Template`, no Jinja |

## Common Pitfalls
1. Phone regex eats UUIDs/dates (s2). Warning sign: `tenant=` ids or timestamps show `[phone]` in message text.
2. Shelling out to `evals.runner` for smoke: exit code 0 on failures.
3. Purge deleting `leads` before `appointments`/`conversations` -> composite FK violation.
4. Forgetting to free `slots.is_booked` when deleting appointments.
5. Filter masks `record.msg` but leaves `args` (re-formats with raw values) -> use `getMessage()` then `args=None`.
6. uvicorn access log bypass (s2).
7. `-partial.md` / `latest.md` report files used as README inputs: untracked/dirty, nondeterministic.
8. Allowlist by line number rather than by file: breaks on every edit.
9. Gate script/test containing the banned words themselves.
10. Purge test hitting dev DB roofing data.

## Code Examples
```python
# logctx.py (sketch)
class PiiMaskFilter(logging.Filter):
    def filter(self, record):
        try:
            record.msg, record.args = mask(record.getMessage()), None
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = mask(record.exc_text)
        except Exception:
            record.msg, record.args, record.exc_info, record.exc_text = "[log message withheld: mask failed]", None, None, None
        return True
```
```python
# retention.py (sketch): one source of truth
PURGED = {"messages": ..., "tool_calls": ..., ...}   # table -> (timestamp col or "via conversation")
KEPT = {"slots": "config", "faq_chunks": "config", "agent_events": "append-only audit, no PII by contract",
        "tenant_api_keys": "credential hashes"}
```

## State of the Art / Environment Availability
No library changes. Environment: g-* compose stack (db 55432, mailpit, n8n, Ollama on host) required for new-business and full pytest; not probed (instruction: no docker/pytest/evals). README says no `.github/`; record that gate/drift run via `make check-shared`, `make g-test`, `make check-n8n` and that CI wiring is deferred.

## Validation Architecture
| Property | Value |
|---|---|
| Framework | pytest (existing), tests in `api/app/test_*.py`, run `make g-test ARGS="app/test_x.py"` |
| Config | existing conftest autouse fixtures (migrations, cleanup) |

| Req | Behavior | Test | Command |
|---|---|---|---|
| OPS-03 | mask cases, filter output, install | unit | `make g-test ARGS="app/test_pii_mask.py app/test_logging_tenant.py"` |
| OPS-04 | purge by age, other tenants untouched, delete_subject counts + audit row without PII, coverage of tables, grants (008) | integration (DB) | `make g-test ARGS="app/test_retention.py"` |
| OPS-06 | gate finds planted hit, allowlist not stale, repo clean | unit | `python3 -m scripts.check_shared` and `make g-test ARGS="app/test_shared_gate.py"` |
| OPS-01 | selection + failure handling with fake run_suite | unit | `make g-test ARGS="app/test_new_business.py"`; manual: `make new-business PACK=bright-smile-dental` by the user |
| OPS-02/07 | drift (docs/generated + README markers) | unit | `make g-test ARGS="app/test_gen_docs.py"` |
| OPS-05 | every tenant_id table appears in docs/data-map.md | unit | `make g-test ARGS="app/test_data_map.py"` |
Wave 0 gaps: all test files above are new; no framework install.

## Security Domain
ASVS: V4 access control (retention admin = super-admin key only; subject delete tenant-scoped via X-API-Key, admin variant explicit tenant), V5 input validation (identifier length/format via Pydantic, parameterized SQL only, never f-string identifier), V7 logging (masking), V8 data protection (retention, deletion; audit stores hash only). Threats: SQLi in delete_subject (bind params), cross-tenant deletion (tx + explicit tenant_id in WHERE), PII in audit (hash only), leaking identifier in endpoint error messages/logs (log counts only).

## Assumptions Log
| # | Claim | Risk if wrong |
|---|---|---|
| A1 | n8n has execution-data pruning env settings usable as a caveat | doc wording only |
| A2 | `drafts.payload` contact key is `contact_email` (seen in the quote-request workflow expression `$json.payload.contact_email`; review_reply keys unverified) | delete_subject misses a draft store; verify in `quotes.py`/`reviews_routes.py` |
| A3 | api container mounts `docs/`, `README.md`, `evals/baselines` | gen_docs must run host-side instead |
| A4 | Python `re` handles the lookahead/lookbehind patterns as written | none (stdlib) |

## Open Questions (with recommended answers)
1. agent_events: purge or keep? Recommend KEEP (append-only, no PII by contract); delete_subject writes an audit row there. If the user wants it purged, 009 adds a SECURITY DEFINER purge function.
2. Retention cutoff on `conversations.started_at` vs `ended_at`? Recommend `COALESCE(ended_at, started_at)`.
3. Past appointments only, or all? Recommend only appointments whose slot `end_time` < now and lead is purged.
4. Smoke subset size ok (escalation + injection ~12-16 scenarios per pack, minutes)? Recommend yes; add `--category` override not needed.
5. Generated docs for roofing and dental both committed? Recommend yes (drift test needs them in repo).
6. "call 144" Swiss emergency number: confirmed publicly as Swiss ambulance number (general knowledge, ASSUMED); keep as pack-level text and flag in data-map caveats as needs review. Deploy env requirements (`PUBLIC_DEMO_TENANT_ID`, `APP_DATABASE_URL`, `TENANT_API_KEYS`, `OWNER_EMAIL`) go in the runbook template.
7. Gate scope: include dashboard shared code? Recommend yes, with `dashboard/app/page.tsx` allowlisted.

## Recommended Plan Split
Wave 1 (parallel, disjoint files):
- **09-01 PII mask + log filter (OPS-03):** `engine/pii.py` (add `mask`) or new `engine/mask.py`, `logctx.py`, `main.py` install (root + uvicorn handlers), `test_pii_mask.py`.
- **09-02 Retention + delete_subject (OPS-04):** `db/migrations/008_retention_grants.sql`, `app/retention.py` (maps, purge, delete_subject), config `retention_days`, endpoints (tenant_admin.py + tenant_routes.py), script entry `scripts/retention.py`, `test_retention.py` (incl. coverage test).
- **09-03 Grep gate (OPS-06):** `scripts/check_shared.py`, two comment FIXes (triage.py, engine/reviews.py), `test_shared_gate.py`, Makefile `check-shared`.
Wave 2 (after wave 1; Makefile edits sequential or trivially merged):
- **09-04 make new-business (OPS-01):** `scripts/new_business.py`, Makefile target, `test_new_business.py`. Depends on 03 only so the new script itself is gate-clean.
- **09-05 gen_docs + README markers (OPS-02, OPS-07):** `scripts/gen_docs.py`, templates, `docs/generated/{summit-roofing,bright-smile-dental}/`, README markers + generated blocks, `test_gen_docs.py`, Makefile `gen-docs`.
Wave 3:
- **09-06 Data map + final gates (OPS-05):** `docs/data-map.md` (stores, processors, retention behaviour, masking limits, dental Art. 9/nFADP, cross-border LLM chain, n8n licence, SMTP/mailpit), `test_data_map.py` reading the table list from 09-02, link from README/runbook template, then run `make check-shared`, `make check-n8n`, `make g-test` as the phase gate (user runs).
