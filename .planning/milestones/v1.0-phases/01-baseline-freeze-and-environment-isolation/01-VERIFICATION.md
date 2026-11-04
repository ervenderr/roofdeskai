---
phase: 01-baseline-freeze-and-environment-isolation
verified: 2026-11-03T00:00:00Z
status: passed
score: 4/4 must-haves verified
---

# Phase 1 Verification

**Goal:** Operator has a machine-checkable definition of "roofing did not change" and a safe place to work.

| Req | Status | Evidence |
|-----|--------|----------|
| BASE-01 | VERIFIED | Lightweight tag `v1-roofing` -> 27a2785. `evals/baselines/v1-roofing.json`: 96 scenarios, meta passed=94/total=96, temperature 0, model llama3.1:8b; only failures are `voice-indecisive`, `voice-over-explainer` (counted from the JSON). `git diff v1-roofing HEAD -- api` shows only the no-op `LLM_TEMPERATURE = 0` constant in llm.py plus the new test file, so the tag has the same roofing behaviour as the baseline. |
| BASE-02 | VERIFIED | `evals/baselines/flake-report.json/.md`: 3 runs, model and temperature pinned, 0 unstable, 2 fail every run (the same two ids), 96 scenarios covered. Runner aborts if a non-local model answers (runner.py ~143). |
| BASE-03 | VERIFIED | `docker-compose.global.yml` overrides host ports (55432, 18025/11025, 15679, 18081); Makefile `GCOMPOSE` uses `-p roofdesk-global`, so volumes are separate (`pgdata` is project-prefixed). `g-up/down/reset/logs/eval` present. The running containers `roofdesk-global-*` sit on the offset ports, none on 5432/8000. I did not inspect the live stack. |
| BASE-04 | VERIFIED | `make eval-gate` -> `g-eval ARGS=--gate`. `runner.gate()` diffs per scenario id against the baseline, reruns each flipped id `RERUNS=2` times, and `decide()` counts a regression only if every rerun fails. It exits 1 with `GATE FAILED: [ids]`. `BASELINE_PATH` override exists. `api/app/test_eval_gate.py`: 8 tests passed (run in the roofdesk-global-api-1 container). |

## Roadmap success criteria
1. Tag and per-scenario baseline: VERIFIED.
2. Flake report from 3 pinned runs: VERIFIED.
3. Isolated stack: VERIFIED statically and by running container ports.
4. Gate fails with differing ids and reruns twice: VERIFIED by unit tests and code reading. The end-to-end `--gate` run was not executed (the full eval takes hours).

## Anti-patterns
None found in phase files (no TBD/FIXME/XXX checked in runner.py, llm.py, test_eval_gate.py, compose file, Makefile targets by reading).

## Notes (non-blocking)
- The tag points at the plan commit 27a2785, not f50d007 (the baseline's `git_sha`). The roofing code is identical between them, so this is fine.
- The tag is lightweight and local. Whether it is pushed was not checked.
- Gate rerun semantics: a "flaky" flag in the baseline does not exempt an id (tested).
