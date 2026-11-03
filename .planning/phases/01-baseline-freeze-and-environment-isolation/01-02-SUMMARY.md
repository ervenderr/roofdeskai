---
phase: 01-baseline-freeze-and-environment-isolation
plan: 02
subsystem: evals
tags: [evals, gate, baseline, flake]
requires: [01-01]
provides: [runner --write-baseline/--flake/--gate, BASELINE_PATH override]
key-files:
  modified: [evals/runner.py, api/app/llm.py]
  created: [api/app/test_eval_gate.py]
requirements-completed: [BASE-01, BASE-02, BASE-04]
---

# Phase 1 Plan 02: Eval runner baseline/flake/gate Summary

evals/runner.py gained `--write-baseline`, `--flake` and `--gate` with tested pure logic (`gate_diff`, `decide`, `baseline_from_results`, `baseline_path`); default behaviour unchanged.

## Tasks
1. Pure gate/baseline logic + runner modes + tests (RED confirmed by ImportError, then GREEN) - commit in git log ("feat: add baseline, flake and gate modes to eval runner").

## Verification (real output)
- `pytest -q` in the roofdesk-global api container: `213 passed` (includes 8 new tests in test_eval_gate.py).
- `python -m evals.runner --help` lists --ids, --category, --write-baseline, --flake, --gate.
- `grep temperature=0 api/app/llm.py`: no match; `LLM_TEMPERATURE = 0` defined and used (behaviour identical).
- The runner modes were NOT run against the live suite (plan 01-03).

## Notes
- Baseline JSON shape: `{"meta": {...}, "scenarios": {id: {passed, category, failed_checks, flaky?}}}`.
- Guard: `assert_local_only` aborts baseline/flake runs if any llm_calls.model lacks the `local:` prefix. Gate does not apply it (plan only required it for baseline/flake).
- Flake report .md is written next to the .json (evals/baselines/flake-report.md).

## Deviations
None.

## Self-Check: PASSED
