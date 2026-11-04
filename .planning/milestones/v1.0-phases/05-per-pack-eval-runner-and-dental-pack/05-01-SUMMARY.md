---
phase: 05-per-pack-eval-runner-and-dental-pack
plan: 01
subsystem: evals
tags: [evals, multi-tenant, packs]
requires: [phase-04]
provides: [ensure_tenant, sync_faq, "--pack runner", per-pack report/baseline/flake paths, scenario validation]
affects: [evals/runner.py, api/app/tenants.py, api/app/pack.py, businesses/summit-roofing/scenarios]
key-files:
  created: [api/app/tenants.py, api/app/test_tenants.py]
  modified: [api/app/pack.py, api/app/test_pack.py, evals/runner.py, api/app/test_eval_gate.py, Makefile]
  moved: [evals/scenarios/*.yaml -> businesses/summit-roofing/scenarios/ (10 files, 96 ids)]
requirements: [EVAL-01, EVAL-02]
metrics:
  completed: 2026-11-04
---

# Phase 5 Plan 01: Per-pack eval runner Summary

`python -m evals.runner --pack <slug>` now resolves the pack's tenant (`ensure_tenant`, `ensure_slots`, `sync_faq`), threads it through every DB touch and `handle_turn`, and writes only that pack's report, baseline and flake files; roofing defaults are unchanged.

## Commits
- 7239562 feat: add ensure_tenant and sync_faq, exclude scenarios from pack hash
- 0fb7cfb feat: per-pack eval runner with tenant threading and scenario validation (includes the 10-file scenario rename)

## Verification
- Red runs shown before implementation: `test_tenants.py` failed at collection (`No module named 'app.tenants'`), `test_pack_hash_ignores_scenarios` failed on a hash mismatch, 14+ runner tests failed with TypeError/AttributeError.
- `make g-test`: 467 passed (before and after the evals).
- Roofing subset gates (local llama3.1:8b, explicit compose exec, run after pytest, pytest rerun after): escalation 8/8, slots 6/6, `regressions: []`, GATE PASSED. `load_scenarios("summit-roofing")` returns 96 ids equal to `v1-roofing.json`; counts 8 escalation / 6 slots.
- `git diff --stat evals/baselines/` empty; `v1-roofing.json` untouched.

## Deviations from Plan
- **assert_local_only timing:** it needs llm_calls from the run, so it executes right after the suite finishes in every mode (plain, gate, flake, write-baseline) and before the report/baseline is written, not before the first scenario.
- **Escalation subset Models line is empty:** all escalations are decided by the regex before any LLM call, so no hosted model could have answered; the slots subset shows `local:llama3.1:8b`.
- Test cleanup: a first pytest run left test tenant rows that blocked `conftest.remove_test_data` (FK on faq_chunks/leads); I removed leftover `test-%` tenants and their rows from the roofdesk-global-db-1 branch DB by hand, after which cleanup ran clean.
- Container has no `git` binary, so tests that go through `write_baseline` set `GIT_SHA`.
- Subset runs rewrote `evals/reports/latest-partial.md` (pre-existing dirty file); not committed.

## Known Stubs
None.

## Self-Check: PASSED
