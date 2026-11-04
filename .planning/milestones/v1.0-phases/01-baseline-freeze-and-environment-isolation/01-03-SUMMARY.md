---
phase: 01-baseline-freeze-and-environment-isolation
plan: 03
subsystem: evals
tags: [baseline, flake, gate]
requires: [01-01, 01-02]
provides: [evals/baselines/v1-roofing.json, flake-report, make eval-gate]
key-files:
  created: [evals/baselines/v1-roofing.json, evals/baselines/flake-report.json, evals/baselines/flake-report.md, evals/reports/v1-roofing.md]
  modified: [Makefile]
requirements-completed: [BASE-01, BASE-02, BASE-03, BASE-04]
---

# Phase 1 Plan 03: Frozen baseline, flake report, gate proof Summary

Real run on the roofdesk-global stack (llama3.1:8b, temperature 0): 94/96, failing ids identical to the pre-change evals/reports/latest.md (`voice-over-explainer`, `voice-indecisive`), so Phase 1 refactors are behavior-neutral. Flake report: 3 runs, 0 unstable ids. Gate proven in both directions.

## Commands
- Phase-wide gate command: `make eval-gate [ARGS="--ids a,b"]` (wraps `g-eval ARGS=--gate`; non-zero exit on regression). `BASELINE_PATH=/srv/evals/baselines/x.json` is forwarded into the container.
- Tag `v1-roofing` = 27a2785, local only, not pushed.

## Results (real)
- Baseline: 96 scenarios, 94 passed, meta sha f50d007, model llama3.1:8b, temp 0, 2026-11-03.
- Flake: 3 full runs, unstable_ids = [], both known failures fail 3/3.
- Gate positive: `make eval-gate ARGS="--ids faq-1,faq-2,esc-human"` -> `GATE PASSED`, exit 0.
- Gate negative (baseline copy marks voice-indecisive passed): 2 reruns shown, `GATE FAILED: ['voice-indecisive']`, regressions: ['voice-indecisive'], exit non-zero (2).
- Improvement (baseline copy marks faq-1 failed, run passes): `improvements: ['faq-1']`, `GATE PASSED`, exit 0 (D-04).
- tmp-flipped.json removed; `git status --short evals/baselines` clean.

## Deviations / notes
- First flake attempt aborted: one local Ollama request timed out, local entered cooldown, Groq fallback answered; the runner's non-local guard correctly aborted ("baseline/flake run is invalid"). Nothing written. Ollama was healthy afterwards, and the identical command was rerun and completed all 3 runs locally. No code patched around it. Risk: Ollama timeouts can recur on long runs.
- The plan's negative test said to flip a passing id to false; that yields an improvement (exit 0), not a regression. Regression was proven by marking a known-failing id as passed in the copy.
- `--ids` takes one comma-separated value, not space-separated.
- flake-report.json has keys `runs`=3, `temperature`, `model`, `unstable_ids`, `pass_counts`; no `flaky` keys were added to the baseline because there are no unstable ids (baseline unchanged by flake step).
- Each eval run overwrites the tracked evals/reports/latest.md; that modified file was deliberately left unstaged and uncommitted (reference copy of the run is evals/reports/v1-roofing.md).

## Self-Check: PASSED
