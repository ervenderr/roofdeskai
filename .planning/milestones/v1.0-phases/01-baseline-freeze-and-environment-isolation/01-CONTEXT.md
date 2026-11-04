# Phase 1: Baseline Freeze and Environment Isolation - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning
**Mode:** --auto (recommended defaults chosen, logged below)

<domain>
## Phase Boundary

Give the operator a machine-checkable definition of "roofing did not change" and a safe place to work: a `v1-roofing` tag, a per-scenario baseline JSON, a 3-run flake report with pinned model and temperature, an isolated compose project/volume for the branch, and a gate command that diffs per-scenario results against the baseline. No product behaviour changes.

</domain>

<decisions>
## Implementation Decisions

### Baseline format
- **D-01:** [auto] Baseline = `evals/baselines/v1-roofing.json`: scenario id -> {passed, category, failed_checks}, plus metadata (git sha, model tag, temperature, date, total/passed counts). Committed to git.
- **D-02:** [auto] The existing `evals/reports/latest.md` is copied to `evals/reports/v1-roofing.md` as the human-readable record. The untracked `latest-partial.md` is left alone.

### Flake measurement
- **D-03:** [auto] Flake report = 3 sequential runs of the full suite with model tag and temperature pinned via env; output `evals/baselines/flake-report.json` and a short markdown summary listing unstable scenario ids. Unstable ids are recorded in the baseline as `flaky: true`.
- **D-04:** [auto] Gate rule: a scenario that differs from baseline is rerun twice; it counts as a regression only if it fails both reruns (for pass->fail), and a fail->pass is reported as an improvement but does not fail the gate. Known flaky ids need 2 of 2 failures too (same rule); no special exemption.

### Gate command
- **D-05:** [auto] `make eval-gate` runs the suite (or `--ids` subset) and exits non-zero listing differing scenario ids. Implemented as a flag/mode in `evals/runner.py` (e.g. `--gate`), not a new tool. Phase 5 adds `--pack`; this phase keeps one pack.

### Environment isolation
- **D-06:** [auto] The branch stack runs as a separate compose project (`COMPOSE_PROJECT_NAME=roofdesk-global`) with its own named volume and non-conflicting host ports via a `docker-compose.global.yml` override or `.env` file. Live deployment config is not touched.
- **D-07:** [auto] Work happens on the local branch `roofdesk-global`. Nothing is pushed and nothing is deployed without asking the operator.

### Roofing-assumption inventory
- **D-08:** [auto] Produce `.planning/phases/01-*/01-ROOFING-INVENTORY.md` listing every roofing-specific item found, including `intake.py` (confirmed: RoofDesk's own sales funnel, stays untenanted) and `prompts/` (agent.v2.md coupling), seeded from `.planning/research/ARCHITECTURE.md`. Documentation only.

### Claude's Discretion
Exact JSON field names, flake-report layout, port numbers, and Makefile target names.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and plan
- `.planning/REQUIREMENTS.md` — BASE-01..04
- `.planning/ROADMAP.md` — Phase 1 goal and success criteria
- `.planning/research/PITFALLS.md` — eval-gate and live-demo pitfalls
- `.planning/research/ARCHITECTURE.md` — unread-file findings, build order step 1
- `/Users/ervenderr/Downloads/RoofDesk Global Platform Spec.md` — Migration plan step 1

### Code
- `evals/runner.py` — scenario loading, scoring, report writing (`latest.md`)
- `evals/scenarios/*.yaml` — the 96 scenarios
- `Makefile` — existing `eval` target
- `docker-compose.yml`, `docker-compose.override.yml` — services, ports, volumes
- `api/app/llm.py`, `api/app/config.py` — model/provider selection and temperature

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evals/runner.py` already runs scenarios through the real agent with deterministic checks and writes a report; the gate and baseline extend it.
- `make eval` runs the suite inside the `api` container.

### Established Patterns
- Evals reset DB state per scenario (`reset_db`), so they must run against the isolated stack, not a shared database.
- Reports are markdown under `evals/reports/`.

### Integration Points
- Model/temperature pinning must go through `settings`/env in `llm.py` (verify how Ollama model tag and temperature are set).
- Host ports 5432, 8000, 8025, 1025, 5679, 8081 are used by the current stack; the isolated stack needs different ones if both run.

</code_context>

<specifics>
## Specific Ideas

- Baseline must record that the roofing pack has exactly 2 known failures (94/96) so later phases can assert the same two.

</specifics>

<deferred>
## Deferred Ideas

- Per-pack baselines and `--pack` flag (Phase 5).
- Nightly eval run workflow (v2).

</deferred>
