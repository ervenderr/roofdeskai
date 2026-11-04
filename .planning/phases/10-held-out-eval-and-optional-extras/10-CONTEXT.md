# Phase 10: Held-Out Eval and Optional Extras - Context

**Gathered:** 2026-11-04 (auto mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver EVAL-06, EXT-01, EXT-02, EXT-03: a published held-out score, an optional Anthropic provider with pinned scorecard runs, connectors exposed as MCP servers, and a third (venue) pack passing its own evals. Local model stays the default. Nothing is pushed or deployed. Roofing and dental pack files and prompts stay byte-identical; the roofing 94/96 and dental 43/43 gates still hold at the end.
</domain>

<decisions>
## Implementation Decisions

### Held-out evals (EVAL-06) - do this FIRST
- **D-01:** Write the 20 held-out scenarios before any other Phase 10 code or tuning, commit them (`evals/heldout/`, separate from the dev sets), then run them exactly once on the local model with the existing runner and publish the score even if low. No scenario edits after the run; failures are reported, not fixed in this phase. The report records the commit SHA that fixed the scenarios and the SHA that ran them, and the score goes into the README scorecard and a doc note.
- **D-02:** The report states the honesty caveat: the scenarios were authored by the same assistant that built the system, with the dev sets visible, so the set is "held out from tuning", not independent. Mix: about 12 roofing and 8 dental, spread over existing categories, worded unlike the dev scenarios. Same deterministic checks as dev sets, no LLM judge.
- **D-03:** One run only. A re-run is allowed only if infrastructure invalidated it (local timeout falling back to a hosted model, `assert_local_only` abort) and must be disclosed.

### Anthropic provider (EXT-01)
- **D-04:** Add `Provider("anthropic", "https://api.anthropic.com/v1/", settings.anthropic_api_key, <model from setting>)` via the existing openai SDK. Active only when `ANTHROPIC_API_KEY` is set and never first in the default chain. Model id from `ANTHROPIC_MODEL`, no constant. Per-provider request shaping: omit `temperature`, use strict `json_schema` not `json_object`, `tool_choice` auto, `n=1`. A 400 from anthropic in a scorecard run must raise loudly, not fall through.
- **D-05:** Scorecard runs use an explicit `providers=[anthropic]` list. The runner gets a flag (for example `--providers anthropic`) that skips `assert_local_only` for that run and labels the report with the model. Fully unit-tested with a fake client; no network in tests.
- **D-06:** No real Anthropic API call by agents in this phase. A real Claude scorecard needs the user's key and cost approval, so the plan ends with a documented command and the README row says "not yet run". Never print or commit keys.

### MCP connectors (EXT-02)
- **D-07:** Add `mcp==2.3.*` as the only new dependency (`MCPServer` from `mcp.server.mcpserver`, name positional, everything else keyword). A thin module exposes the existing connector adapter classes (sheet, accounting, bookings, ads) as MCP tools, labelled mock, with an explicit tenant argument; no new connector logic. Stdio via `python -m scripts.mcp_server`; mounting in FastAPI only if trivial. Research must confirm the v2 in-process test client. Dependency install and image rebuild happen on the branch stack only, with the pip resolution output shown.

### Venue pack (EXT-03)
- **D-08:** Third pack `businesses/<slug>/` (fictional venue/experience business with staff and group bookings), built from the existing demo-venue fixture plus the qualification, FAQ, escalation and messages needed to run the agent. Uses services (group-tier quotes), capacity (staff rota) and intake mappings. Own scenarios (about 30 across applicable categories plus quote/capacity/intake checks), baseline, per-pack gate, README scorecard row via gen_docs, generated SOPs and runbook. Goal: no category under 90%, escalation recall 100%; if the local 8B falls short, report honestly.
- **D-09:** Roofing and dental files untouched; pack-hash pin tests get the new pack's hash deliberately; the grep gate still applies to shared code only; `make new-business PACK=<venue>` must pass.

### Order
- **D-10:** Strictly sequential plans: held-out (write, commit, run once) -> venue pack + evals -> Anthropic provider (code only) -> MCP -> final gates (g-test, check-n8n, check-shared, gen-docs drift, roofing 94/96, dental 43/43, venue gate, module evals). The held-out run happens before anything touches shared prompts or code, so it measures the system as of Phase 9.

### Claude's Discretion
Held-out scenario content, venue slug/name, scenario counts, MCP tool naming, plan split (expect about 7 plans).

### Open items carried in
- Confirm "call 144" Swiss emergency number; deploy requirements; Co-Authored-By trailers on two Phase 3 commits (local, unpushed); n8n licence decision; Phase 8 `Check key` loop abort.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` Phase 10; `.planning/REQUIREMENTS.md` EVAL-06, EXT-01..03
- `/Users/ervenderr/Downloads/RoofDesk Global Platform Spec.md` (held-out test, MCP, Anthropic, third pack)
- CLAUDE.md STACK notes (Anthropic compat limits, MCP v2 gotchas)
- `api/app/llm.py`, `api/app/config.py`, `api/app/engine/connectors.py`, `evals/runner.py`, eval scenario files, demo-venue fixture under `api/app/tests_data/`, `api/app/test_pack_modules.py`, `scripts/gen_docs.py`, `scripts/new_business.py`
</canonical_refs>

<code_context>
## Existing Code Insights

- Runner supports `--pack`, `--gate`, `--ids`, `--flake`, `assert_local_only`; baselines via `default_baseline_path`.
- demo-venue fixture pack exists for engine-module tests; conftest creates and cleans its tenant.
- Connector adapters and mocks exist from Phase 7; MCP is a thin wrapper.
- gen_docs and the README scorecard iterate `businesses/*/pack.yaml`, so a new pack appears after `make gen-docs`.
</code_context>

<deferred>
## Deferred Ideas

- Real Claude scorecard run (needs user key and cost approval); real connectors; Agent Office; Flight Recorder; supplier-order.
</deferred>
