---
phase: 09-docs-pii-retention-and-make-new-business
plan: 06
subsystem: docs
tags: [data-map, ops-05, final-gate]
requires: [09-05]
provides: [docs/data-map.md, api/app/test_data_map.py]
key-files:
  created: [docs/data-map.md, api/app/test_data_map.py]
  modified: [README.md, evals/reports/latest.md]
requirements-completed: [OPS-05]
---

# Phase 9 Plan 06: Data map and final gates Summary

Factual data map (stores, processors, retention, log masking, caveats marked "needs review") with a test that requires every tenant table (plus tenants, tenant_api_keys) and every PURGED/KEPT key to appear. README links it and lists the check targets, noting there is no CI runner.

## Commits
- 6ccd093 docs: data map and check targets
- bb6b21d chore: refresh roofing eval report after phase 9 gate (evals/reports/latest.md only: date, SHA, latency)

## Verification
- RED seen: test_data_map failed with FileNotFoundError before the doc existed; green after (2 passed).
- README edit: `make gen-docs` showed only the README prose change, generated blocks unchanged.

## Final gates (strictly serial, exit codes)
1. `make g-test`: 1207 passed, exit=0
2. `make check-n8n`: 31 passed, exit=0
3. `make check-shared`: OK, 11 allowlisted files, exit=0
4. `make gen-docs`: exit=0, `git diff --stat docs/generated README.md` empty
5. Roofing gate (`python -m evals.runner --gate` in the api container, model warmed keep_alive 6h, LLM_TIMEOUT_S=300, runner re-seeds slots via ensure_slots): Models local:llama3.1:8b, 94/96, failures exactly voice-over-explainer and voice-indecisive, improvements [], new [], flaky-pass [], regressions [], GATE PASSED, exit=0
6. Dental gate (`--pack bright-smile-dental --gate`): 43/43, regressions [], GATE PASSED, exit=0
7. `make g-eval-modules`: quote 27/27, capacity 13/13, brief 16/16, reviews 45/45, intake 17/17, exit=0
8. `make new-business` both packs: skipped, covered by plan 09-04 evidence (bright-smile-dental exit 0 12/12; summit-roofing exit 0 16/16 on second run). No code changed since that affects it besides docs/tests.
- `git status --short businesses prompts evals/baselines`: empty.
- pytest was not run during any eval; no code changes after the evals.

## Deviations from Plan
None. The first batch of exit codes was lost to a zsh PIPESTATUS quirk, so steps 1-4 were rerun with plain `$?` (all 0).

## Not verified
- No legal review: all legal items are flagged "needs review" only.
- EXECUTIONS_DATA_PRUNE behaviour of n8n not checked (doc says verify).
- Hosting region of the ovh endpoint not checked.
- new-business not re-run in this plan.

## Self-Check: PASSED
