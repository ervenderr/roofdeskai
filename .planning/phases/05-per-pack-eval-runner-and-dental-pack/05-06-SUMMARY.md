---
phase: 05-per-pack-eval-runner-and-dental-pack
plan: 06
subsystem: evals
tags: [eval, regression-gate, dental, flake]
requires: [05-05]
key-files:
  created: [evals/baselines/bright-smile-dental-flake.json, evals/baselines/bright-smile-dental-flake.md]
  modified: [evals/reports/latest.md, evals/reports/bright-smile-dental.md]
requirements: [EVAL-01, EVAL-02, EVAL-03, EVAL-04]
metrics:
  completed: 2026-11-04
---

# Phase 5 Plan 06: Final regression proof Summary

Roofing gate through `--pack summit-roofing --gate` is 94/96 with the same two failures and regressions []; dental gate is 43/43 regressions []; dental flake (3 runs) found 0 unstable scenarios.

## Roofing gate (git sha eaab4ca, local llama3.1:8b, LLM_TIMEOUT_S=300)
- Exit 0, `Overall: 94/96`, `Models: local:llama3.1:8b` only, `GATE PASSED`.
- Failures exactly `voice-over-explainer` and `voice-indecisive`; `improvements: []`, `new: []`, `flaky-pass: []`, `regressions: []`.
- Categories: voice 14/16 (88%), all others 100%. Gates: min category 88%, escalation recall 11/11.
- v1-roofing.json and flake-report.* untouched (git diff empty). latest.md committed (151b4a8).

## Dental gate and flake (sha 151b4a8)
- `--pack bright-smile-dental --gate`: 43/43, every category 100% (disqualified 4, escalation 8, faq 5, injection 4, out_of_knowledge 4, out_of_order 3, qualified 4, slots 4, vague 3, voice 4), recall 9/9, regressions [], GATE PASSED.
- `--pack bright-smile-dental --flake`: 3 full runs, unstable 0, failed-every-run 0. Flake files are `bright-smile-dental-flake.json/.md`; dental baseline JSON unchanged (no flaky marks to write). Committed fba34b9.

## pytest
- `make g-test` before the evals: 497 passed.
- After the dental evals (nothing running concurrently): first run 1 failed, 496 passed (failing test id not captured; same intermittent behaviour noted in 05-05). Two consecutive reruns: 497 passed, 497 passed. Cause not identified; it has appeared twice, both right after an eval run (leftover state suspected). Flagging, not fixed.

## Requirement deviations
- D-05: Mon-Sat became Mon-Fri. The engine supports only weekdays_only or all seven days; the pack FAQ says Monday to Friday; clients/bright-smile-dental.yaml updated accordingly in plan 02.
- D-13: no roofing iso-* eval scenarios. Roofing isolation is pytest only (plan 04); dental carries dinj-other-business and dook-roofing.
- D-11 satisfied by accepting both `reply_forbid` and `forbid_reply_regex` names.
- "call 144" is an ASSUMED Swiss emergency number in a fictional clinic; user to confirm.
- FAQ-steering sentences were added to dental faq.yaml during tuning (05-05): service_type extraction hints. Retrieval-dependent; a durable fix is a prompt/engine change.
- Shared prompt `prompts/agent.v2.md` contains a static "Denver" extraction example, so dental prompts contain "Denver". Template text, not tenant data; unchanged to protect the roofing gate. Possible Phase 9 cleanup.
- CHF alternative added to the shared unsupported_claim regex; always_human is data only.
- Known limits: 4-digit Swiss postcodes and umlauts in address_status, single-digit spoken Swiss house numbers, `{business}` loader/runtime mismatch.
- Dental runs (metrics_json carries `pack`) appear in the admin eval trend alongside roofing runs.
- Intermittent pytest failure: see pytest section.

## ROADMAP Phase 5 criteria
1. `--pack` writes per-pack report/baseline/flake, never overwriting another pack's: plan 01 tests; after dental gate and flake, `git diff` on v1-roofing.json and flake-report.json is empty.
2. Roofing 94/96, same two failures: above.
3. Dental 43 scenarios, no category under 90% (min 100%), emergency recall 9/9: above.
4. Zero leakage: 9 isolation tests (plan 04) plus dinj-other-business and dook-roofing passing in the dental gate.

## Commits
- 151b4a8 docs: update roofing eval report after per-pack runner
- fba34b9 docs: add bright-smile-dental flake report
