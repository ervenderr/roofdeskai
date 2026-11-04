# Phase 10: Held-Out Eval and Optional Extras - Research

**Researched:** 2026-11-04
**Domain:** eval tooling (YAML scenarios, runner), OpenAI-compat provider shaping, MCP Python SDK 2.3, third business pack
**Confidence:** HIGH on repo facts and Anthropic/MCP behaviour (read from code and current docs, MCP verified in a scratch venv); MEDIUM on how the 8B model will score venue scenarios

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Write the 20 held-out scenarios before any other Phase 10 code or tuning, commit them (`evals/heldout/`, separate from the dev sets), then run them exactly once on the local model with the existing runner and publish the score even if low. No scenario edits after the run; failures are reported, not fixed in this phase. Report records the commit SHA that fixed the scenarios and the SHA that ran them; score goes into the README scorecard and a doc note.
- D-02: Honesty caveat in the report: authored by the same assistant that built the system, dev sets visible, so "held out from tuning", not independent. Mix about 12 roofing and 8 dental, spread over existing categories, worded unlike the dev scenarios. Same deterministic checks, no LLM judge.
- D-03: One run only. Re-run allowed only if infrastructure invalidated it (local timeout falling back to a hosted model, `assert_local_only` abort) and must be disclosed.
- D-04: Add `Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, <model from setting>)` via the openai SDK. Active only when `ANTHROPIC_API_KEY` is set, never first in the default chain. Model id from `ANTHROPIC_MODEL`, no constant. Per-provider shaping: omit `temperature`, strict `json_schema` not `json_object`, `tool_choice` auto, `n=1`. A 400 from anthropic in a scorecard run must raise loudly, not fall through.
- D-05: Scorecard runs use explicit `providers=[anthropic]`. Runner flag (e.g. `--providers anthropic`) skips `assert_local_only` for that run and labels the report with the model. Unit-tested with a fake client; no network in tests.
- D-06: No real Anthropic call by agents. Plan ends with a documented command; README row says "not yet run". Never print or commit keys.
- D-07: `mcp==2.3.*` is the only new dependency (`MCPServer` from `mcp.server.mcpserver`, name positional, rest keyword). Thin module exposes the existing connector adapters (sheet, accounting, bookings, ads) as MCP tools, labelled mock, with an explicit tenant argument; no new connector logic. Stdio via `python -m scripts.mcp_server`; FastAPI mount only if trivial. Confirm v2 in-process test client. Install/rebuild on the branch stack only, with pip resolution output shown.
- D-08: Third pack `businesses/<slug>/` (fictional venue with staff and group bookings) from the demo-venue fixture plus qualification, FAQ, escalation, messages to run the agent. Uses services, capacity, intake mappings. About 30 own scenarios plus quote/capacity/intake checks, baseline, per-pack gate, README scorecard row via gen_docs, generated SOPs and runbook. Goal: no category under 90%, escalation recall 100%; if the 8B falls short, report honestly.
- D-09: Roofing and dental files untouched; pack-hash pin tests get the new pack's hash deliberately; grep gate applies to shared code only; `make new-business PACK=<venue>` must pass.
- D-10: Strictly sequential: held-out (write, commit, run once) -> venue pack + evals -> Anthropic provider (code only) -> MCP -> final gates (g-test, check-n8n, check-shared, gen-docs drift, roofing 94/96, dental 43/43, venue gate, module evals).

### Claude's Discretion
Held-out scenario content, venue slug/name, scenario counts, MCP tool naming, plan split (about 7 plans).

### Deferred Ideas (OUT OF SCOPE)
Real Claude scorecard run; real connectors; Agent Office; Flight Recorder; supplier-order.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-06 | 20 held-out scenarios written before tuning, run once, score published | Section 1: loader reuse, `--heldout` mode, run-once guard, naming |
| EXT-01 | Anthropic optional provider; scorecard pins `providers=[anthropic]` | Section 2: exact `llm.py` diff, contextvar pin, runner flag |
| EXT-02 | Connectors exposed as MCP servers (mcp 2.x) | Sections 3-4: verified API, in-process test, tool wrapper design |
| EXT-03 | Third pack passes own evals using quotes, capacity, intake | Section 5: pack file list, tests, docs pickup, pitfalls |
</phase_requirements>

## Summary

Everything needed already exists except four small seams. (1) The runner reads scenarios only from `businesses/<slug>/scenarios/` and would write held-out results over `latest-partial.md` / `<slug>-partial.md`; it needs a `--heldout` mode with its own scenario dir, its own report path and a refuse-second-run guard. (2) `agent.py` calls `llm.chat(messages)` with no `providers` argument in 4 places, so "pass `providers=[anthropic]`" cannot be done by argument threading; use a `ContextVar` pin in `llm.py` that `chat()` consults. (3) `_call` currently sends only `messages` and `temperature=0` (no `response_format`, no `tool_choice`, no `n`), so Anthropic needs exactly one shaping change: omit `temperature`. The json_schema/tool_choice/n rules in D-04 are already satisfied by omission. (4) The demo-venue fixture is already a nearly complete pack (all 6 required files plus services, capacity, connectors); the real pack is mostly a copy with a different slug plus 30 scenarios and tuning.

mcp 2.3.0 resolves cleanly against `api/requirements.txt` on Python 3.12 (uv dry resolve): fastapi stays 0.115.14, starlette 0.46.2, pydantic 2.14.2, httpx stays 0.27.2, httpx2 2.16.0 is added alongside. `mcp.client.Client(server)` is the in-process test client and works from plain sync pytest through `anyio.run` (no pytest-asyncio needed). Verified in a scratch venv.

**Primary recommendation:** Do plan 1 (scenarios + `--heldout` tooling, committed) before touching anything else, run once in plan 2, then venue pack, then Anthropic, MCP, final gates. Never name the real venue pack `demo-venue` (conftest deletes that tenant's data).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary | Rationale |
|------------|-------------|-----------|-----------|
| Held-out scenario loading/run-once guard | Eval tooling (`evals/runner.py`) | filesystem | Not a request path; host-mounted `./evals` |
| Provider pin + request shaping | API/Backend (`llm.py`) | runner | All LLM calls go through `llm.chat` |
| MCP connector tools | Standalone stdio process (`scripts/mcp_server.py`) | API container | Wraps pure adapters; no DB, no n8n |
| Venue pack data | Pack files (`businesses/<slug>`) | DB tenant row | Config, not code |
| Scorecard/docs | `scripts/gen_docs.py` | README markers | Reads committed baselines only |

## Standard Stack

### Core
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| mcp | 2.3.0 (pin `mcp==2.3.*`) | MCP server + in-process client | Official SDK; PyPI `requires_python >=3.10`, `pydantic>=2.12`, `httpx2>=2.10`, `starlette>=0.27`, `sse-starlette>=3.0`, `uvicorn>=0.31.1` [VERIFIED: pypi.org/pypi/mcp/2.3.0/json] |
| openai (existing) | 1.* (1.109.1 resolves) | Anthropic via compat endpoint | No new dependency [CITED: platform.claude.com OpenAI SDK compat page] |

No other new packages. `anyio` (transitive of mcp and openai) is used to run async MCP tests from sync pytest.

**Installation (branch stack only):** add `mcp==2.3.*` to `api/requirements.txt`, then `make g-up` (rebuild). Show `pip` output in the plan summary.

**Resolution evidence (uv pip compile, py3.12, requirements + mcp==2.3.\*):** fastapi 0.115.14, starlette 0.46.2, pydantic 2.14.2, pydantic-core 2.50.2, httpx 0.27.2, httpx2 2.16.0, mcp 2.3.0, mcp-types 2.3.0, uvicorn 0.32.1, anyio 4.16.0, sse-starlette 3.0.3, new transitives: pyjwt 2.15.1, cryptography 50.0.2, jsonschema 4.26.0, opentelemetry-api 1.45.2, python-multipart 0.0.33. Without mcp the same resolve gives fastapi 0.115.14 / starlette 0.46.2 / pydantic 2.14.2, so nothing existing moves. [VERIFIED: uv dry resolve this session]

## Package Legitimacy Audit

| Package | Registry | Age | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-------------|-----------|-------------|
| mcp | PyPI | official SDK; releases 2.0.0b1 ... 2.3.0 | github.com/modelcontextprotocol/python-sdk | not run (no pip in this shell) | Approved: named in the spec and official docs. Planner: show `pip` resolve output at install; no `checkpoint:human-verify` needed beyond the user-approved dependency in D-07 |

Removed: none. Flagged: none. slopcheck was unavailable, so the `[VERIFIED]` here rests on official docs plus PyPI metadata, not slopcheck.

## 1. Eval scenarios, loader, held-out design

**Format** [VERIFIED: evals/runner.py]: `businesses/<slug>/scenarios/<category>.yaml`, each a list of `{id, category, turns[], expect{}, setup?, steal_slot_before_turn?}`. `load_scenarios(slug)` globs `settings.businesses_dir/slug/scenarios/*.yaml` sorted, rejects duplicate ids, unknown category, unknown keys, unknown expect keys, empty turns. File name need not match category.
- Categories (10): `voice qualified faq disqualified vague out_of_knowledge injection out_of_order escalation slots`.
- Expect keys: `state state_in outcome lead_status lead_status_not tools no_tools reply_forbid reply_require forbid_reply_regex require_reply_regex` (reply patterns use `re.search` per reply, no flags, use `(?i)`).
- `--pack` picks `businesses/<slug>`; baseline `evals/baselines/<slug>.json` (roofing `v1-roofing.json`), flake `<slug>-flake.json`, report `evals/reports/<slug>.md` (roofing `latest.md`), partial runs `-partial.md`. Gate only needs the baseline file.
- Dev counts: roofing 96 (ids `qual-*, disq-*, faq-*, ook-*, inj-*, esc-*, slot-*, ooo-*, vague-*, voice-*`), dental 43 (ids all start with `d`, pinned by `test_dental_pack.COUNTS` and `len==43`). Roofing 94/96 failures: `voice-over-explainer`, `voice-indecisive`.
- Dev wording: roofing uses "missing shingles after the storm", "123 Maple St, Denver", "Sam Reyes, phone 303-555-0142", owner/timeline asked in rule order; dental uses Zurich streets (Rosenweg 12, Marktgasse 5), "Anna Keller, 044 555 0142", ordinal slot picks ("The first one"). Voice sets use lowercase, spoken digits. Held-out should vary: different cities inside each area (roofing: aurora/lakewood/arvada/centennial/littleton; dental: winterthur/baden/uster/dietikon), different names/streets, facts given in a different order or all in one message, new FAQ topics phrased differently, new escalation phrasings that are not copies of dev ones, different injection tricks. Do not copy dev turns and do not grep the safety regex to craft misses (that would be tuning); write them naturally and let failures stand.

**Recommended held-out layout:** `evals/heldout/<pack-slug>/<category>.yaml` (same schema, ids prefixed `ho-r-*` roofing and `ho-d-*` dental so they never collide with dev ids). 20 total: roofing 12 (qualified 2, disqualified 2, faq 1, vague 1, out_of_knowledge 1, injection 1, out_of_order 1, escalation 1, voice 2... pick any 12 spanning categories; slots 1 instead of one of the above is fine) and dental 8 (qualified 1, disqualified 1, faq 1, out_of_knowledge 1, injection 1, escalation 1, slots 1, voice 1). Held-out dir is outside `businesses/`, so `pack_hash` (which skips only `scenarios/`) is unaffected, and `check_shared` does not scan `evals/heldout` (ROOTS lists `evals/runner.py`, `evals/outreach_runner.py`, `evals/modules` only).

**Runner changes needed (minimal):**
1. `load_scenarios(slug, root: Path | None = None)`: `root` defaults to `settings.businesses_dir / slug / "scenarios"`; heldout passes `HERE / "heldout" / slug`. Same validation, so typos still fail.
2. New mutually exclusive mode `--heldout`; incompatible with `--write-baseline/--gate/--flake/--ids/--category` (argparse error). It must run the full set for that pack.
3. Reports/results: do not call `report_path()` for heldout (it would write `latest-partial.md` / `<slug>-partial.md`, clobbering a dev partial). Give `write_report` an optional `out: Path`; heldout writes `evals/reports/heldout-<slug>.md`. Never write a baseline JSON, never touch `latest.md`.
4. Run-once guard: write machine record `evals/heldout/results/<slug>.json` `{scenarios_sha, run_sha, model, date, passed, total, per-scenario pass/fail+failed_checks, reruns: []}`. If it exists, `sys.exit` unless `--force-rerun "<reason>"`; with the flag, append `{reason, date}` to a `reruns` list and keep the old file as `<slug>.prev.json` (disclosure per D-03). Also refuse when `--heldout` is combined with a non-local provider; keep `assert_local_only` and, on abort, write nothing (so an infra-invalidated run does not consume the single run; the abort happens before the write).
5. SHAs: the api image has no git, and `_git_sha()` shells out to `git` (raises `FileNotFoundError` in the container if `GIT_SHA` unset). The existing Makefile target passes `GIT_SHA`. Add a Makefile target `g-heldout` that computes on the host `HELDOUT_SHA=$(git log -1 --format=%h -- evals/heldout)`, fails if `git status --porcelain evals/heldout` is non-empty (enforces "committed before run"), and passes both `-e GIT_SHA` and `-e HELDOUT_SHA`. Also store a sha256 of the heldout files in the result as a tamper check.
6. Add a unit test that fails if any heldout scenario id equals a dev id, that heldout YAMLs validate via `load_scenarios`, counts are 12/8, and the guard refuses a second write (fake `run_suite`, tmp dir, same style as `test_eval_gate.py`).
7. `evals/runner.py` is a check_shared ALLOW entry with exactly 19 hits. New code must not contain the banned words (`roo` + `f` not followed by "desk", `sum`+`mit`, `den`+`ver`); if the `ROOFING` constant is reused no new hit appears. Run `make check-shared` after editing.

**Publishing:** README: add prose (outside the `<!-- BEGIN GENERATED -->` markers, which gen_docs overwrites and test_gen_docs drift-checks) such as a "Held-out score" paragraph next to the existing "Read this with the right amount of salt" caveat, plus `docs/heldout-eval.md` note with both SHAs, per-category, failures listed, the D-02 caveat, and the disclosure of any re-run. `test_drift_readme` asserts the string `Latest run: **94/96 scenarios**` exists and that generated blocks match; keep both untouched. Do not extend `scorecard_block` for heldout (it would change generated output and drift tests).

## 2. `api/app/llm.py` (read in full) and Anthropic

Current behaviour [VERIFIED: file read]:
- `Provider(name, base_url, api_key, model, cooldown_until=0.0)` dataclass; `PROVIDERS = [local, groq, nvidia, gemini, openrouter, ovh]`. Keyless providers are skipped in `chat()` (`if not p.api_key`). Local api_key is `"ollama"` if `LOCAL_LLM_URL` set else `""`.
- `_call(p, messages)`: `OpenAI(base_url, api_key, timeout=settings.llm_timeout_s, max_retries=0)` then `chat.completions.create(model, messages, temperature=LLM_TEMPERATURE)` where `LLM_TEMPERATURE = 0`. No `response_format`, `tool_choice`, `n`, `max_tokens`. Returns `{content, model: f"{p.name}:{p.model}", prompt_tokens, completion_tokens, latency_ms}`.
- `chat(messages, providers=PROVIDERS)`: loops; `BadRequestError` -> warning, next provider, NO cooldown; any other `OpenAIError` (429, 5xx, timeout, 401) -> `cooldown_until = now + provider_cooldown_s` (60s), next; all exhausted -> `RuntimeError("all LLM providers failed or are cooling down")`. Note `providers=PROVIDERS` default is bound at def time, i.e. the same list object.
- Callers: `agent.py` x2 (`_faq_answer`, `_ask_llm`), `intake.py`, `outreach.py` x2, `quotes.py`, `reviews_routes.py`, `triage.py`; none pass `providers`. So the agent cannot receive `providers=[anthropic]` by argument without touching 8 call sites.
- `llm_calls.model` stores `"<name>:<model>"`; `assert_local_only` requires every model to start with `local:`.
- `run_suite` catches every `Exception` per scenario and records `error: ...` as a failed scenario, so a raised provider error today becomes a silently failing scenario, not a crashed run.
- `config.py` has `groq_api_key` etc. but no anthropic fields; `SECRET_HINTS` masks any setting whose name contains "key", so `anthropic_api_key` is auto-masked in reprs. `docker-compose.yml` passes `GROQ_API_KEY: ${GROQ_API_KEY:-}` explicitly, so add `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` there and to `.env.example` (blank). Check the `env_file` behaviour of the compose files before assuming `.env` flows through.

**Anthropic compat facts** [CITED: platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk, fetched this session]: base URL `https://api.anthropic.com/v1/`; `temperature` 0-1 but on Claude 4.7+ any value below 1 returns 400, so omit; `top_p` other than default 400 (we do not send it); `n` must be 1; `response_format` only `json_schema` with `strict: true` (`json_object`/`text` -> 400); `tool_choice` forced modes 400 on Opus/Sonnet 5.5, Fable 5.1, Mythos 5.1 (we send none); system messages hoisted; no prompt caching; `max_tokens` is not required by the compat examples; Claude 5 models have thinking on by default and the compat layer does not return thinking text. Listed model ids include `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-sonnet-5-5`, `claude-haiku-5-5`.

**Exact changes:**
1. `config.py`: `anthropic_api_key: str = ""`, `anthropic_model: str = "claude-haiku-4-5-20251001"` (cheap tier default as config, overridable by `ANTHROPIC_MODEL`; not a code constant).
2. `llm.py`: add field `send_temperature: bool = True` to `Provider` (after `cooldown_until`, so positional construction in `test_llm.py` still works); `_call` builds `kw = {"temperature": LLM_TEMPERATURE} if p.send_temperature else {}`. Append `Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, settings.anthropic_model, send_temperature=False)` as the LAST entry of `PROVIDERS` (never first; keyless = skipped).
3. Loud failures: add `class ProviderRejected(RuntimeError)`; in `chat()` for an `anthropic`-pinned call re-raise instead of falling through. Simplest: field `strict: bool = False` on `Provider` (True for anthropic) and in the `except BadRequestError` branch `if p.strict: raise ProviderRejected(f"{p.name} rejected the request: {e.status_code}") from e`. In `run_suite` add `except ProviderRejected: raise` before the generic `except Exception` so the run aborts instead of recording 96 "error:" failures. Rationale: otherwise a 400 on every call looks like a score of 0.
4. Pin without touching call sites: `_pinned: ContextVar[list[Provider] | None]`; `chat(messages, providers=None)` uses `providers if providers is not None else (_pinned.get() or PROVIDERS)`; context manager `pinned(providers)` sets/resets it. Change the signature default from `PROVIDERS` to `None` (existing tests pass explicit lists, unaffected; `main.py` uses the default). Also check `grep PROVIDERS` for other readers before changing (only llm.py references it in non-test code).
5. Runner: `--providers NAME[,NAME]` (`choices` from `{p.name for p in llm.PROVIDERS}`); resolve to Provider objects; `sys.exit` with a clear message if a chosen provider has no key (chat() would otherwise skip it and raise a generic RuntimeError). Wrap the whole run in `with llm.pinned(chosen):`. Replace `assert_local_only` for that run with `assert_only_provider(cids, t, prefix="anthropic:")`, which keeps the contamination guard (stricter than just skipping it) and still aborts on any other model. Disallow `--providers` together with `--write-baseline`, `--gate`, `--flake`, `--heldout` so a hosted run can never overwrite the local baselines. Report path: `evals/reports/provider-<slug>-<provider>.md` (new name; never `latest.md`), report line `Models:` already comes from `llm_calls`, and meta `temperature: None`.
6. Preflight: before the suite, one `llm.chat([{"role":"user","content":"reply ok"}], chosen)` so a bad key/model aborts in one call with the status code, not 96 failed scenarios. This is the only real network call and it only happens when the user runs the command.
7. Tests (fake client, no network): monkeypatch `llm.OpenAI` with a recorder; assert the anthropic call omits `temperature` and local includes `temperature=0`; assert a fake `BadRequestError` on a strict provider raises `ProviderRejected` while a non-strict one falls through; assert `pinned([a])` makes `chat()` with no argument use `a` only and that cooldown on `a` does not fall back to default `PROVIDERS`; assert runner flag parsing and the `--providers` + `--gate` rejection.
8. Documented command (D-06): `make g-eval ARGS="--pack summit-roofing --providers anthropic"` with `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL` in `.env`. README row text "not yet run".

Pitfall: embeddings (`embed()`) always use the local Ollama and are not in `llm_calls`; FAQ retrieval therefore stays local even in an anthropic scorecard. State that in the report line.

## 3. MCP Python SDK 2.3 [VERIFIED in scratch venv + docs]

- Install `mcp==2.3.*`; Python >=3.10 (Docker `python:3.12-slim` fine). Works with the existing pins as shown above. `httpx2` coexists with `httpx==0.27.*`; do not bump httpx.
- Server: `from mcp.server.mcpserver import MCPServer` (also exposed as `from mcp.server import MCPServer`; both import). `mcp = MCPServer("roofdesk-connectors")`; pass everything except name by keyword. `@mcp.tool()` on plain sync or async functions; type hints and docstring become schema and description. `mcp.tool(name="...")(fn)` also works for generated tools.
- Run on stdio: `mcp.run(transport="stdio")` (verified end to end with a stdio `Client`). Transport options belong on `run()` for http, not on the constructor.
- Return shape: a bare `dict` return gives `structured_content=None` and the JSON as `TextContent` (verified); only typed returns (pydantic model, TypedDict, dataclass) produce structured content. Tests should therefore `json.loads(result.content[0].text)` or define a pydantic return model. Recommended: return a pydantic model so the tool schema is explicit and `structured_content` is populated (verify once in the plan's RED test).
- In-process test client: `from mcp import Client` (also `mcp.client.Client`); `async with Client(mcp_server) as c: await c.list_tools(); await c.call_tool(name, args)`. This replaces v1 `create_connected_server_and_client_session` [CITED: py.sdk.modelcontextprotocol.io/migration]. Bad arguments do not raise: the result has `is_error=True` and a pydantic validation message in `content` (verified). Run from sync pytest with `anyio.run(coro)`; the repo has only `pytest` (no pytest-asyncio), so do not add it.
- Gotchas from CLAUDE.md STACK still apply for the optional FastAPI mount (session_manager in lifespan, DNS-rebinding 421). Recommendation: skip the mount (not trivial); ship stdio only, per D-07.
- Run path in the container: `python -m scripts.mcp_server` works because `./scripts` is mounted at `/srv/scripts` and WORKDIR is `/srv` (same as `python -m scripts.run_flows`). Importing `app.*` from scripts is the established pattern (`new_business.py`). Do not write to stdout from the module (stdio protocol); log to stderr only.

## 4. Connector classes [VERIFIED: engine/connectors.py]

- `Connector` Protocol: `name: str`, `fetch(tenant: TenantRef, day: date) -> ConnectorResult`. `TenantRef(slug, tenant_id, tz)` frozen dataclass. `ConnectorResult(name, source="mock", ok=True, metrics: Mapping[str, Decimal], error: str|None, bookings: tuple[(aware UTC datetime, covers)])`.
- Adapters: `BookingsMock`, `SheetMock`, `AccountingMock`, `AdsMock` built from a `SourceCfg` (pack `connectors.yaml` source entry with `mock.offsets` / `mock.unavailable`); data seeded from `sha256(slug:name:day)`, deterministic across processes. `REGISTRY` maps name -> class; `METRICS` fixed display keys; `fetch_source(cfg, tenant, day)` never raises (returns `ok=False, error=<type name>`); `fetch_all`.
- Selection: a pack lists sources in `connectors.yaml` (`sources: [{name, mock?}]`, `brief: {send_hour, tolerance}`); `pack.connectors.sources` feeds `fetch_all` (brief engine, `/brief` routes). A pack with no `connectors.yaml` has `pack.connectors is None`.
- MCP wrapper design (thin, no new logic): `scripts/mcp_server.py` with 4 tools `fetch_sheet`, `fetch_accounting`, `fetch_bookings`, `fetch_ads`, each `(tenant: str, day: str) -> ConnectorOut`. Body: `pack = load_pack(tenant)` (validates slug via SLUG_RE and raises `PackError` for unknown tenants), find `cfg` in `pack.connectors.sources` by name (if missing, return `ok=False, error="NotConfigured"` rather than inventing a config), `TenantRef(pack.slug, "mcp", pack.meta.timezone)` (mock ignores tenant_id; no DB access), `res = fetch_source(cfg, ref, date.fromisoformat(day))`. Output: `{source: res.source ("mock"), ok, error, metrics: {k: str(Decimal)}, bookings: [[iso_utc, covers]]}`; always include `"source": "mock"` and mention "MOCK data" in each tool description. Decimals as strings (JSON, and consistent with the Decimal-only money rule). `fetch_source` already swallows adapter errors to a type name, preserving "never leak internals".
- Tests (`api/app/test_mcp.py`, no DB): list_tools returns the 4 names; call each against the demo-venue fixture (point `settings.businesses_dir` at the fixtures via monkeypatch, as `packs_dir` fixture does) and compare to `fetch_source` output directly (proves it wraps, not reimplements); unavailable source (`ads` in the fixture has `mock.unavailable`) returns `ok=False`; unknown tenant slug and malformed date give `is_error` or `ok=False`, never a traceback; every result says `mock`.
- Security note for the plan: stdio tool takes any pack slug, so it reads any tenant's mock data. Acceptable because it is local-process, mock, and deterministic; real connectors must add auth before this is exposed over HTTP.

## 5. Venue pack (third pack)

**Fixture inventory** (`api/app/tests_data/packs/demo-venue/`, 9 files [VERIFIED]): `pack.yaml` (slug, business, kind, offer, timezone Europe/Zurich, locale en-CH, reviews block, intake maps waiver/checkin/result), `calendar.yaml` (slot_hours 10,12,14,16,18; 60 min; 14 days; weekdays_only false), `qualification.yaml` (ONE rule: service_type in_list [escape_room, private_event], synonyms, non_business_pattern, never-match owner patterns, stopwords), `escalation.yaml` (safety regex injury/ambulance/fire/bleeding/fainted; always_human), `faq.yaml` (3 entries), `messages.yaml` (complete, valid), `services.yaml` (CHF, escape_room per_person 35.00 min 2 with add-ons and group_discount tiers plus corporate surcharge; private_event flat 600; team_building per_hour; vip_experience, line truncated in my read), `capacity.yaml` (3 shifts incl. a deliberately odd `sunday_night` 00:00-06:00 test shift), `connectors.yaml` (bookings, sheet with +3 offset, accounting, ads `unavailable: true`, brief send_hour 7).

**Loader requirements** [VERIFIED: pack.py]: required files `pack calendar qualification escalation messages faq`; optional `services capacity connectors`; all models `extra="forbid"`; `messages.ask` keys must equal rule ids + `{"name","phone or email"}` exactly; `closed` keys exactly DONE/DISQUALIFY/ESCALATE; template fields enforced (`owner_alert_body` MUST contain name, when, phone, email, address, need; `offer_slots` prefix+options; etc.); `business/kind/offer` must not contain `{{` or `<<`; prompt templating via `render()` replaces only `{{business}} {{kind}} {{offer}} {{service_enum}}`; an unresolved `{{` raises. So the fixture's messages already satisfy the loader; the fixture already "runs" the agent in principle.

**What the real pack needs beyond a copy of the fixture:**
- New slug/name (fictional, no "Demo"); suggest `puzzle-peak` / "Puzzle Peak Escape". NEVER `demo-venue`: `conftest.py` deletes `agent_events`, `drafts`, `capacity_flags`, `brief_runs`, `intake_people` for slug `demo-venue` at session end and `packs_dir`/`venue_tenant` copy the fixture under that slug; reusing it would make the real pack's data test-owned and the `packs_dir` copy collide. Also run `grep -rn "demo-venue" api scripts evals` to confirm the fixture name is not assumed to be unique elsewhere (it is hardcoded in `evals/modules/loader.py` `DEFAULT_PACK`, test_connectors, test_capacity, test_gen_docs which copy the fixture, not the real pack).
- Qualification: keep `service_type` as the only rule, or add a second in_list/`in_area` rule only if a scenario needs disqualification beyond "unsupported service" (dental added `address in_area`). For the venue, disqualification comes from `service_type == other` (e.g. wedding catering, gift cards via `non_business_pattern`). RULE_FIELDS limits: in_list fields `service_type|property_type|budget_range`, yes_no `is_owner`, max_number `timeline_months`, in_area `address`; there is no party-size rule, so group size is not qualified in chat (it is priced through the services/quote module). State this in the pack README/docs.
- FAQ: 8-12 entries with explicit facts (hours, location, group size 2-30, age limits, cancellation, accessibility, parking, what is not offered, payment/prices NOT stated in chat if the dev scenarios forbid prices; dental's FAQ explicitly tells the model that service names are `service_type`, not a name, and what `other` means: copy that technique for escape-room/event wording). Prices live in services.yaml, not FAQ, so `out_of_knowledge` price questions must produce the safe fallback (mirror `dook-price` with `reply_forbid` on CHF amounts).
- Escalation: venue safety regex for injury, fire, medical, allergic reaction, fainting, lost child, harassment, plus generic human/angry/legal come from `policy._GENERIC_ESCALATION`; messages.closed ESCALATE already says "call 144" (Swiss ambulance; open item "confirm 144" in CONTEXT; keep consistent with dental and flag again). Dental's regex is a long single-quoted alternation; keep escalation scenarios recall at 100% deterministic by adding a test like `test_scenario_recall_is_deterministic_and_total` and `test_no_other_scenario_turn_escalates` (policy.escalation_reason with pack) so recall is proven without the LLM.
- Messages: copy fixture; replace the fixture's `owner_alert_body` problem: venue has no address rule, so `lead["address"]` is `None` and `_notify_booking` formats `Address: None` into the owner email. Options: (a) one-line change in `agent._notify_booking` `address=lead["address"] or "-"` (roofing/dental always have an address, so no gate effect; recommended), (b) accept "None". See open question 3.
- Capacity: replace the fixture's test-oriented `sunday_night` shift with realistic venue shifts; keep at least one shift whose min_staff can be violated so capacity evals have a flag case. Connectors: realistic (no `unavailable`, no offset) or keep one offset to exercise tolerance; the brief eval cases for the real pack should state which.
- Calendar: weekdays_only false, Zurich wall-clock hours (same as fixture).
- `pack.yaml`: keep `reviews` and `intake` blocks (they exercise `/reviews` and `/intake-event`), set `owner_email` unset.

**How dental was built (analogy)** [VERIFIED: git log, files]: pack files first, 43 scenarios written BEFORE tuning (`3e888f4 test: add 43 ...`), then `fix: tune dental pack iteration 1/2` (FAQ and regex edits only, never shared code), baseline written via `--pack bright-smile-dental --write-baseline`, flake report `bright-smile-dental-flake.*`, `test_dental_pack.py` with shape/regex/scenario-count tests (`COUNTS` dict, ids prefixed `d`), PINNED hash added. Venue should copy this: ids prefixed `v`, `test_venue_pack.py` with a `COUNTS` dict.

**Scenarios (about 30)**: categories applicable: qualified (4), disqualified (3), slots (3), faq (4), escalation (5), injection (3), out_of_knowledge (4), out_of_order (2), vague (2), voice (3). Include at least: group request ("12 of us, birthday") must not produce a price or discount in chat; "do you have wheelchair access" faq; corporate/team-building ask routes to `private_event` or `other` per synonyms; no-slot nurture; slot taken; cross-pack isolation probes (mention roofing/dental) mirroring `dook-roofing`/`dinj-other-business`. `new_business.select_smoke` requires `escalation` and `injection` categories to exist.

**Module checks for the venue (quote/capacity/intake):** `evals/modules/loader.py` resolves `pack:` only from `tests_data/packs` (`_pack` uses `load_pack(c.get("pack", DEFAULT_PACK), base=PACKS)`). To add cases on the real pack, change `_pack` to try `PACKS` then fall back to `settings.businesses_dir` (3 lines) and add ~8 cases (`pack: puzzle-peak`) across quote (group tier boundaries 9/10/19/20, corporate surcharge, missing price -> needs_human), capacity (understaffed shift, covers over `max_covers`), intake (waiver/checkin/result mapping). Case counts are printed in the README scorecard line by gen_docs (counts top-level entries of each `cases.yaml`), so README and drift change once; no test pins those counts [VERIFIED: grep test_module_evals].

**Where the new pack is picked up automatically** [VERIFIED]:
- `gen_docs._slugs` = every `businesses/*/pack.yaml`; `render_all` writes `docs/generated/<slug>/runbook.md` + 10 SOPs; `scorecard_block` reads `default_baseline_path(slug)` and raises `FileNotFoundError` if the baseline is missing, so the baseline must be committed BEFORE running `make gen-docs`, else gen_docs and the drift tests fail. Run `make gen-docs` and commit `docs/generated/<slug>/` and README.
- `test_gen_docs`: `PACKS` from the real `businesses/` dir; `test_key_set`, `test_drift_generated_docs`, `test_drift_readme` require generated files and README to be current. They fail until `make gen-docs` is committed.
- `test_pack_modules.PINNED` (dict of slug -> sha256; `pack_hash` covers every file under the pack except `scenarios/`); add the venue hash as the LAST step of venue tuning (every FAQ edit changes it, as dental's did). `test_shipped_packs_have_no_modules` is parametrized over `PINNED` and asserts `services/capacity/connectors is None`; do NOT add the venue to `PINNED` blindly: that test would fail because the venue has all three. Either add a separate `PINNED_VENUE` hash test or split the dict (recommended: add `PINNED_WITH_MODULES = {slug: hash}` with its own hash test and a "modules present" assertion).
- Tests that iterate `businesses/*`: only `test_gen_docs` (listing) and `new_business.cross_tenant_check` (iterates tenant rows with pack_slug; skips packs that fail to load). Tests that hardcode the two real packs (`test_isolation`, `test_new_business` pair fixture, `test_intake_event` loop, `test_triage`) create their own tenants and do not enumerate, so a third pack does not break them. `test_tenants`/`test_tenant_me` use `demo-venue` as the "other" tenant: unaffected.
- Dev DB: `make new-business PACK=<slug>` / the runner call `ensure_tenant(slug)` which inserts a persistent tenant row (like dental); conftest only removes `test-%` and `demo-venue` tenants, so the venue tenant persists and `test_data_map` (tables named in docs) is unaffected (no schema change).
- `check_shared`: ROOTS exclude `businesses/`, `evals/heldout`, `tests_data`, so pack words cannot trip it; shared code you add (runner, llm, scripts/mcp_server.py, test files are skipped by `test_` prefix) must avoid the three banned words. `scripts/` is a scanned root, so `scripts/mcp_server.py` must not contain them (do not hardcode "summit-roofing" in examples; use the venue slug or a placeholder).
- `make new-business PACK=<slug>` needs `escalation` + `injection` scenarios and passes `assert_local_only`; it creates no report.
- README per-pack numbers come only from `evals/baselines/<slug>.json`, written by `python -m evals.runner --pack <slug> --write-baseline` (non-roofing needs no `--force-baseline`).

## Architecture Patterns

### Flow (held-out run)
```
evals/heldout/<slug>/*.yaml --load_scenarios(root)--> run_suite (handle_turn, local LLM)
   -> assert_local_only -> results/<slug>.json (run-once guard) + reports/heldout-<slug>.md
   -> README paragraph + docs/heldout-eval.md (manual, outside generated markers)
```
### Flow (provider pin)
```
runner --providers anthropic -> preflight chat() -> with llm.pinned([anthropic]):
   agent -> llm.chat(messages) -> ContextVar -> only anthropic; 400 -> ProviderRejected -> run aborts
   -> assert_only_provider("anthropic:") -> reports/provider-<slug>-anthropic.md
```
### Anti-patterns
- Editing a held-out scenario or adding a dev scenario copy of it after the run (violates D-01).
- Threading `providers=` through 8 call sites or mutating `llm.PROVIDERS` globally (leaks into later runs; use the ContextVar).
- Letting `--providers` coexist with `--write-baseline/--gate/--flake` (hosted answers into committed baselines).
- Putting the pack slug as `demo-venue`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| MCP protocol/transport | JSON-RPC over stdio by hand | `MCPServer` + `Client` from mcp 2.3 |
| Anthropic client | `anthropic` SDK adapter | existing `openai` SDK + compat endpoint |
| Scenario validation | new schema | `evals.runner.load_scenarios` (add a root arg) |
| Money formatting in tool output | floats | `str(Decimal)` |
| Docs/scorecard | hand-edited tables | `make gen-docs` |

## Common Pitfalls

1. **Held-out run consumes itself on an infra fault.** A local timeout falling back to groq makes `assert_local_only` abort. Write the result file only after that assert, and keep the model warm (Phase 9 used `keep_alive 6h`, `LLM_TIMEOUT_S=300`); a disclosed re-run via `--force-rerun` is the only allowed second run.
2. **Overwriting dev reports.** `report_path` for a partial roofing run is `latest-partial.md`; the working tree already has uncommitted `evals/reports/latest-partial.md`, `bright-smile-dental-partial.md` and a modified `bright-smile-dental.md` (git status). Heldout and provider runs must use new filenames; do not commit those pre-existing dirty files in Phase 10 commits (stage by path).
3. **Silent anthropic fall-through.** Today `BadRequestError` -> next provider; with `providers=[anthropic]` that becomes the generic RuntimeError, then `run_suite` records it as scenario failures. Needs `ProviderRejected` + re-raise (Section 2).
4. **Thinking/latency/cost on Claude 5 models**: thinking on by default through compat; use the haiku default for scorecards.
5. **Pack hash drift**: any stray file (`.DS_Store`) in `businesses/<slug>/` changes `pack_hash` (and the pin). Pin last.
6. **`address: None` in owner alert** for packs without an address rule (Section 5).
7. **gen_docs before baseline** raises FileNotFoundError and breaks three tests.
8. **`PINNED` parametrization** asserts no modules; adding the venue there fails (Section 5).
9. **mcp stdio and stdout**: any `print` corrupts the protocol.
10. **Container image has no git**: `_git_sha()` raises if `GIT_SHA` is unset; pass SHAs from the host.
11. **check_shared counts** on `evals/runner.py` (19) and new shared files.
12. **8B model on venue**: dental took two tuning iterations; allow 2-3, tune only pack files (FAQ wording/regex), never prompts/shared code, then report honestly if a category stays under 90%.

## Code Examples

```python
# llm.py (shape of the pin) -- [ASSUMED design, standard contextvars usage]
from contextlib import contextmanager
from contextvars import ContextVar
_pinned: ContextVar[list[Provider] | None] = ContextVar("pinned_providers", default=None)

@contextmanager
def pinned(providers: list[Provider]):
    tok = _pinned.set(providers)
    try:
        yield
    finally:
        _pinned.reset(tok)

def chat(messages, providers=None):
    providers = providers if providers is not None else (_pinned.get() or PROVIDERS)
    ...
```
```python
# scripts/mcp_server.py -- API verified this session (mcp 2.3.0, py3.12)
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("connectors")

@mcp.tool(name="fetch_ads", description="MOCK ads metrics for a tenant pack and ISO date")
def fetch_ads(tenant: str, day: str) -> ConnectorOut: ...

if __name__ == "__main__":
    mcp.run(transport="stdio")
```
```python
# test (no pytest-asyncio needed) -- verified
import anyio, json
from mcp import Client
def test_tools():
    async def go():
        async with Client(mcp) as c:
            r = await c.call_tool("fetch_ads", {"tenant": "x", "day": "2026-01-01"})
            return r.is_error, json.loads(r.content[0].text)
    assert anyio.run(go)[0] is False
```

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer` (v2) | web examples are wrong |
| `create_connected_server_and_client_session` | `mcp.client.Client(server)` | in-process tests |
| temperature=0 for determinism | omit on Claude 4.7+ | one-line provider shaping |

## Runtime State Inventory
Not a rename phase. Notes: new tenant rows persist in the dev DB after `new-business`; `eval_runs`/`eval_results` rows are inserted by every report (heldout rows too, `pack` metric = slug; acceptable, but tag heldout in the report text since metrics `pack` is the same string as dev runs).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ContextVar pin design is sufficient (agent runs sync in one thread; no executor hop inside `handle_turn`) | 2 | Pin lost in a worker thread; check `handle_turn` has no `run_in_executor`/thread pool before relying on it |
| A2 | Default `anthropic_model` haiku-4-5-20251001 is acceptable as a config default | 2 | User may prefer an empty default; then provider inactive until set |
| A3 | The 8B model reaches >=90% per category on venue scenarios | 5 | D-08 allows honest reporting if not |
| A4 | `services.yaml` vip_experience entry is complete in the fixture (my cat output looked truncated at `unit: per_person`, probably missing price; test_quote covers it) | 5 | Real pack must give it a price or the quote returns NeedsHuman, which may be intended |
| A5 | "call 144" Swiss emergency wording | 5 | carried open item |

## Open Questions (with recommended answers)

1. **Heldout via runner flag vs scenario copy.** Recommend `--heldout` in `runner.py` (Section 1). The runner change is shared code but touches no prompts; disclose it in the held-out doc as "tooling added before the run; measured system otherwise as of Phase 9". Commit tooling and scenarios together in plan 1 so the recorded scenarios SHA is the exact tree that runs.
2. **Replace vs skip `assert_local_only` for anthropic.** Recommend replace with `assert_only_provider("anthropic:")` (satisfies D-05's intent, keeps the guard).
3. **`Address: None`.** Recommend the one-line `or "-"` in `agent._notify_booking` and a test; roofing/dental unaffected (verify with gate). If the user wants zero shared-code change in plan 3, accept "None" and note it.
4. **Venue slug.** Recommend `puzzle-peak` (not `demo-venue`).
5. **Is the held-out score "one number"?** Two runs (roofing 12, dental 8) each once; publish combined X/20 plus per-pack. Neither pack is run twice.
6. **Should `ANTHROPIC` be in default `PROVIDERS` at all?** Recommend yes, appended last (skipped without a key), so `llm.PROVIDERS` lookups by name work for `--providers`. If the user prefers zero chance of hosted Claude answering production chats, build the provider only inside the runner instead.
7. **Do scenarios in `evals/heldout/` need to be mounted?** `./evals:/srv/evals` is already a rw mount in the base compose; the global override does not remove it. [VERIFIED docker-compose.yml].

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Docker / g-stack | all gates | not probed (instructed not to run docker) | `make g-up` needed for mcp rebuild |
| Ollama llama3.1:8b | held-out, venue evals | not probed | warm model, `LLM_TIMEOUT_S=300` as in Phase 9 |
| uv (host) | resolve dry-run | yes | used for evidence only |
| ANTHROPIC_API_KEY | real scorecard | not provided | D-06: documented command only |

## Validation Architecture

| Property | Value |
|----------|-------|
| Framework | pytest 8.* via `make g-test` (docker, ~1207 tests today) |
| Quick run | `$(GCOMPOSE) exec -T api python -m pytest -q app/test_llm.py app/test_eval_gate.py app/test_mcp.py` |
| Full suite | `make g-test` |

| Req | Behavior | Test | File |
|-----|----------|------|------|
| EVAL-06 | heldout dir loads, 12/8, unique ids, guard refuses 2nd write, report path != dev paths | unit | `app/test_heldout.py` (Wave 0) |
| EXT-01 | anthropic omits temperature; strict 400 raises; pin; runner flag exclusivity | unit (fake client) | extend `app/test_llm.py`, `test_eval_gate.py` |
| EXT-02 | 4 tools, wrap `fetch_source`, mock label, bad args | unit (anyio + Client) | `app/test_mcp.py` (Wave 0) |
| EXT-03 | pack loads, shape, recall total, no false escalation, counts, pinned hash, docs drift | unit + eval | `app/test_venue_pack.py` (Wave 0), `make g-eval ARGS="--pack <slug> --gate"`, `make g-eval-modules` |

Wave 0 gaps: the three new test files above. Sampling: per-task targeted pytest; per-plan `make g-test`; phase gate = D-10 final list.

## Security Domain

| ASVS | Applies | Control |
|------|---------|---------|
| V5 Input validation | yes | MCP tool args validated by pydantic from hints, slug via `SLUG_RE`, date via `fromisoformat`, runner slug via `load_pack` |
| V6 Cryptography | no | none added |
| V7/V8 Secrets & logging | yes | `anthropic_api_key` auto-masked by `Settings.__repr_args__`; never log request headers; `.env.example` blank value only |
| V4 Access control | note | MCP stdio reads any pack's mock data; local-only; add auth before any HTTP exposure |

Threats: key leakage via traceback (mitigated by masked repr; do not put the key in exception text); hosted data egress during a "local" run (mitigated by pin + provider assertion); scorecard contamination (pin + preflight + strict 400).

## Recommended plan split (7 sequential plans)

1. **10-01 Held-out scenarios + tooling (commit).** Write 20 scenarios in `evals/heldout/`; add `load_scenarios(root)`, `--heldout`, run-once guard, `write_report(out=)`, `make g-heldout`, `test_heldout.py`; `make check-shared` unchanged count; commit; record scenarios SHA. No pack/prompt change.
2. **10-02 Run once and publish.** Preconditions: clean tree, Ollama warm. `make g-heldout` for roofing and dental (one run each), write `docs/heldout-eval.md`, README paragraph, SHAs, honesty caveat, failures listed untouched. Checkpoint: user confirms the model is up.
3. **10-03 Venue pack files + scenarios (before tuning).** `businesses/<slug>/` (9 files), ~30 scenarios, `test_venue_pack.py` (shape, regex recall, no false escalation, counts), `evals/modules/loader.py` fallback + ~8 module cases, optional `_notify_booking` `or "-"`. `make new-business` smoke may wait for plan 4.
4. **10-04 Venue tuning, baseline, docs.** Run, tune pack files only (max 2-3 iterations), `--write-baseline`, flake, per-pack gate, pin hash (separate `PINNED` structure), commit baseline BEFORE `make gen-docs`, commit docs/generated + README, `make new-business PACK=<slug>`.
5. **10-05 Anthropic provider (code only).** Settings, `Provider` fields, `_call` shaping, `ProviderRejected`, `pinned`, runner `--providers`, preflight, `assert_only_provider`, env/compose/.env.example, tests with fake client; README row "not yet run" and the documented command.
6. **10-06 MCP connectors.** Add `mcp==2.3.*`, `make g-up` rebuild with resolve output, `scripts/mcp_server.py`, `test_mcp.py`, README/docs usage (stdio command, tool list). No FastAPI mount.
7. **10-07 Final gates.** `make g-test`, `check-n8n`, `check-shared`, `gen-docs` drift, roofing gate 94/96 with the same two failures, dental 43/43, venue gate, `g-eval-modules`, `git status` shows businesses/summit-roofing, businesses/bright-smile-dental and prompts unchanged; summary with the held-out numbers.

## Sources

### Primary (HIGH)
- Repo files read: `evals/runner.py`, `api/app/llm.py`, `api/app/config.py`, `api/app/engine/connectors.py`, `api/app/pack.py`, `api/app/conftest.py`, `api/app/test_pack_modules.py`, `test_dental_pack.py`, `test_gen_docs.py`, `test_new_business.py`, `test_llm.py`, `scripts/gen_docs.py`, `new_business.py`, `check_shared.py`, `evals/modules/loader.py`, demo-venue fixture, dental/roofing pack files and scenarios, Makefile, compose files, Phase 9 summaries.
- https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk (fetched 2026-11-04)
- https://py.sdk.modelcontextprotocol.io/migration/ (MCPServer, Client, testing section) and https://github.com/modelcontextprotocol/python-sdk
- https://pypi.org/pypi/mcp/2.3.0/json (requires_dist, python), uv dry resolve with the repo requirements, scratch-venv run of MCPServer + Client (in-process and stdio) on Python 3.12.

### Tertiary
- Not verified: behaviour of `Client` structured_content with pydantic return types (only dict return observed); real Anthropic responses (no API call made).

## Metadata
**Research date:** 2026-11-04. **Valid until:** about 2026-12-04 (mcp releases frequently; model ids change).
