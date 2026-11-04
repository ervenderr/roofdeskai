---
phase: 10-held-out-eval-and-optional-extras
verified: 2026-11-04
status: passed
score: 4/4 success criteria verified (with caveats below)
---

# Phase 10 Verification

**Goal:** An honest, published held-out score, then the optional platform extras.
Static checks only (git diff, grep, json reads). pytest, evals and docker were NOT run by this verifier.

## Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 20 held-out scenarios written before tuning, run once, score published | VERIFIED | `evals/heldout/` has 20 scenario ids (roofing 12, dental 8). `git diff --name-status 6fc701f HEAD -- evals/heldout` shows only the two results files added, so scenarios are frozen. Results: summit-roofing 10/12, bright-smile-dental 7/8 = 17/20, `reruns: []` in both, `scenarios_sha256` identical, precheck `git diff --quiet 6fc701f HEAD -- api prompts businesses scripts evals/runner.py` recorded as exit 0. Published in README.md line 53 and docs/heldout-eval.md, including the 3 failures left unfixed. |
| 2 | Anthropic selectable, local stays default, scorecard pinned with no fallback | VERIFIED | `api/app/llm.py`: `Provider("anthropic", ...)` appended last in PROVIDERS, keyed by `settings.anthropic_api_key` (default ""), model from `settings.anthropic_model`. `pinned()` context var limits `chat()` to pinned providers. `evals/runner.py` `--providers anthropic` exits if no key and is rejected with `--write-baseline/--gate/--flake/--heldout`. `git grep sk-ant` outside markdown: no hits. No real call was made. |
| 3 | Connectors callable as MCP servers wrapping the same adapters | VERIFIED | `scripts/mcp_server.py` uses `MCPServer` (mcp 2.x import path) and wraps `app.engine.connectors.fetch_source` plus `load_pack`; errors return `ConnectorOut(ok=False)`. `api/app/test_mcp.py` exists and covers list_tools, parity with `fetch_source`, unavailable source and bad input. Test not executed here. |
| 4 | Venue pack passes its own evals using quotes, capacity, intake | VERIFIED (static) | `businesses/puzzle-peak/` has the full pack (pack, qualification, services, capacity, calendar, connectors, escalation, faq, messages, 10 scenario files). `evals/baselines/puzzle-peak.json` has 33 scenarios, all 33 passing. 10-07 summary reports it at 100% per category at the final gate. Not re-run by me. |
| - | Roofing, dental, prompts unchanged | VERIFIED | `git diff --stat 985199e HEAD -- businesses/summit-roofing businesses/bright-smile-dental prompts` is empty. |

## Requirements
EVAL-06, EXT-01, EXT-02, EXT-03: all satisfied by the evidence above. REQUIREMENTS.md still shows them Pending and ROADMAP checkboxes are unticked; the orchestrator should update them.

## Caveats (honest, not blockers)
- Held-out scenarios were authored by the same assistant that built the system, with dev sets visible. They are held out from tuning, not independent. The README says so.
- The Claude scorecard was NOT run (no key committed or used). The path is wired and guarded only; EXT-01 asks for selectability, not a score.
- Venue `disqualified` scenarios (vdisq-catering, vdisq-job, vdisq-giftcard) are flaky on local llama3.1:8b. 33/33 is a snapshot, and a rerun may show 1 to 3 failures there.
- SQLAlchemy version drift (noted in the summaries) is unresolved. It is not verified here and does not affect the above.
- `.planning/config.json` is modified and untracked report/showcase files exist in the working tree; unrelated to this phase.

## Anti-patterns
No unreferenced TBD/FIXME/XXX checked beyond targeted greps; none seen in the files read.

## Gaps
None.
