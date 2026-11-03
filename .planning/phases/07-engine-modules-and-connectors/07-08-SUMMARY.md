---
phase: 07-engine-modules-and-connectors
plan: 08
subsystem: evals
tags: [evals, module-evals, regression-gate]
requires: [07-07]
provides: [python -m evals.modules, evals/modules/{quote,capacity,brief,reviews,intake}/cases.yaml, make g-eval-modules, api/app/test_module_evals.py]
key-files:
  created: [evals/modules/__init__.py, evals/modules/__main__.py, evals/modules/loader.py, evals/modules/quote/cases.yaml, evals/modules/capacity/cases.yaml, evals/modules/brief/cases.yaml, evals/modules/reviews/cases.yaml, evals/modules/intake/cases.yaml, api/app/test_module_evals.py]
  modified: [Makefile, evals/reports/latest.md]
requirements-completed: [EVAL-05]
metrics: {tasks: 2, commit: cdfb7ab}
---
# Phase 7 Plan 08: Module evals and phase gates Summary

Deterministic, LLM-free and DB-free eval sets for the five engine modules (118 cases) with a strict loader, CLI and pytest wrapper, then the phase regression gates: full pytest 1044 passed, roofing 94/96 with the same two failures, dental 43/43.

## Commits
- cdfb7ab `test: deterministic module eval sets and runner` (Task 1)
- Roofing report and this summary are separate docs commits (hashes in the final report).

## Task 1: module evals (real output)
- RED: `make g-test ARGS="app/test_module_evals.py -q -x"` -> `Interrupted: 1 error during collection` (no `evals.modules.loader`).
- `make g-eval-modules` (exit 0):
  ```
  quote: 27/27 passed
  capacity: 13/13 passed
  brief: 16/16 passed
  reviews: 45/45 passed
  intake: 17/17 passed
  ```
- `make g-test ARGS="app/test_module_evals.py -q"`: all dots (123 tests: 118 named cases plus 5 per-module `failed == 0` checks).
- Negative check: changing one expected total made the CLI print `FAIL quote:tier-10-gets-10pct: total 315.00 != 316.00` and exit non-zero; reverted.
- Loader is strict: unknown top-level or expect keys, unknown kind, missing keys and duplicate ids fail the load. `run(module)` is shared by the CLI and pytest. Pytest ids are `module:case-id`.
- Coverage: quote (tiers 9/10/19/20, corporate percent and fixed, per_hour, add-ons, missing price, qty below min, unknown add-on/service, missing qty, rule_unevaluable, qty_not_applicable, total == sum asserted on every case, 9 text_check cases incl. injection and date-not-an-amount); capacity (all three flag kinds, boundary, hard max_covers, override, four DST windows Denver/Zurich spring+fall chosen so a naive 6h window gives the wrong answer, one 5-run new/unchanged/reflagged/resolved/recurs sequence); brief (disagreement, tolerance, unavailable, error text not leaked, currency, mock labelling, mock end-to-end, 8 `is_due` rows incl. spring-forward); reviews (>= 4 per code, benign, apology, ratings 1..5, injection, health_privacy on/off); intake (duplicate, replay, out-of-order, case-different email, phone normalisation, missing key, wrong types, bad event leaves person untouched).

## Task 2: gates (run strictly one at a time)
- (a) `make g-test` (full): `1044 passed, 1 warning in 21.02s`. Includes the roofing/dental hash-pin test.
- (b) llama3.1:8b warmed (`keep_alive 6h`), roofing slots re-seeded with `ensure_slots`, then in the background with `LLM_TIMEOUT_S=300` (not committed): `python -m evals.runner --pack summit-roofing --gate` -> exit 0
  ```
  - Git SHA: cdfb7ab  Prompt: agent.v2  Models: local:llama3.1:8b
  - Overall: **94/96** scenarios passed
  Gates: min category 88%, escalation recall 11/11
  - voice-over-explainer: state COLLECT != DONE; outcome None != booked; ... missing tool call book_appointment
  - voice-indecisive: state BOOK != DONE; outcome None != booked; ... missing tool call book_appointment
  improvements: []   new (not in baseline): []   flaky-pass: []   regressions: []
  GATE PASSED
  ```
  Booking validity 100%, escalation 11/11 / 11/11, schema validity 95% over 232 LLM calls, p50/p95 8.2s / 11.2s.
- (c) dental slots re-seeded, then `--pack bright-smile-dental --gate` -> exit 0: `Models: local:llama3.1:8b`, `Overall: **43/43** scenarios passed`, `regressions: []`, `GATE PASSED`.
- (d) `git status --short businesses` empty; `evals/baselines/*` unchanged; no prompt files other than the three Phase 7 ones (`quote-extract.v1.md`, `quote-email.v1.md`, `review-reply.v1.md`) added since the phase started.

## Decisions
- `run()` and the per-module runners live in `loader.py` (the plan's file list has no separate runner module).
- Reviews `rating` is a required case field, but `check_reply` has no rating parameter, so "identical across 1..5" is structural; the cases document it, and `test_reviews.py` inspects the source for rating branches.
- Case files for reviews use JSON-style rows (valid YAML) because they were generated.

## Deviations from Plan
- [Rule 1 - own error] The hand-computed total in a draft quote case (440.00) and several draft review texts were wrong/unclear; fixed the cases, not the checkers. The planned "rounding half-up" case is replaced by `discount-applies-to-service-line-only`: no half-cent is reachable with the fixture prices (all multiples of 0.50); half-up is pinned in `api/app/test_quote.py`.
- Sequence case "flag outside range is not resolved" was dropped from the eval set (needs two different ranges; covered in `test_capacity_api.py`).
- Roofing gate used `-e LLM_TIMEOUT_S=300` on the command line only. `evals/reports/latest.md` (roofing) is committed; the dental report and `*partial*.md` are not.

## Limits / not verified
- The review `unknown_fact` heuristic (40% vocabulary threshold plus `REVIEW_GENERIC`) is calibrated on fixtures only; real model output may over-flag to needs_human.
- Dental has no `reviews` block, so its `health_privacy` path is exercised only through the fixture pack.
- The admin `X-Tenant-Id` fallback is unchanged (not revisited here).
- No real-LLM run of the quote extraction/email or review prompts; module evals are fakes-free but LLM-free by design.
- Module evals use the `demo-venue` fixture pack only, not shipped packs (shipped packs have none of these blocks).
- Concurrency and RLS behaviour are covered by the module test files, not by these evals.

## Known Stubs
None.

## Self-Check: PASSED
Files exist, commit cdfb7ab present, both gates exited 0 with `regressions: []`.
