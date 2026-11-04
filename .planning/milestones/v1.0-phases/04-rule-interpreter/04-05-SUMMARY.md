---
phase: 04-rule-interpreter
plan: 05
subsystem: qualification
tags: [freeze, deletion, eval-gate]
requires: [04-04]
provides: [frozen zero-diff digests; old qualification path deleted; gate 94/96]
key-files:
  created: [api/app/tests_data/frozen_qualify.py]
  modified: [api/app/policy.py, api/app/pack.py, api/app/test_policy.py, api/app/test_pack.py, api/app/test_qualify_diff.py, api/app/test_agent.py]
metrics:
  tests: "441 passed"
---

# Phase 4 Plan 05: Freeze, delete old path, full gate Summary

SHA-256 digests of the old functions' results were frozen and committed first, then the old path was deleted; qualify.* still reproduces the digests and the full local gate holds 94/96.

## Commits
- ccac792 test: freeze qualification diff digests from old path
- 2fcc917 test: repoint policy tests to qualify, drop old-path oracle tests
- 28fb575 refactor: delete old qualification path and compat properties

## Frozen digests (computed from the old functions, old and new both reproduced them before deletion)
- GRID_SHA256 0e1d734f158af3ebb5cc931be89dac2e4aa5ad9b9e5bdb44514bea77f69b5161 (GRID_COUNT 84_720)
- ADDR_SHA256 da7a8912ee5b1ada5c3297f7cd089209f1facd23c88b4f2cd443e600052f01fb (ADDR_COUNT 10_052)
- Pre-deletion `make g-test ARGS="app/test_qualify_diff.py -q"`: 6 passed.

## Deletion
- policy.py: removed address_status, qualification, missing_fields, next_question; _tokens, has_contact, grounding, escalation, claims, slot picking kept.
- pack.py: removed service_area, qualifying_services, max_timeline_months compat properties (service_types kept).
- Tests removed as superseded: test_zero_diff_grid, test_address_zero_diff, test_frozen_digest_old (digest test_frozen_digest_new + count assertions supersede them), test_pack.test_compat_properties (test_rule_params_frozen supersedes), test_agent.test_agent_uses_qualify_not_policy (it monkeypatched the deleted functions; the old path no longer exists and other agent tests cover the flow).
- test_policy.py repointed to qualify.qualify / address_status(cities, a) / missing_fields.
- Grep gate: `git grep -nE "qualifying_services|max_timeline_months|service_area|def address_status|def qualification|ASK_KEYS"` prints only qualify.py's own address_status and a test_pack.py rule-name string (`service_area_not_lower`, a test case id). Business-words grep prints nothing.
- `make g-test`: 441 passed.

## Gate (local-only, llama3.1:8b warmed keep_alive 6h, hosted keys blanked, LLM_TIMEOUT_S=300, git sha 28fb575)
Overall 94/96, Models: local:llama3.1:8b, booking validity 100%, escalation 11/11 / 11/11, schema validity 95% over 232 calls. Failures exactly voice-over-explainer and voice-indecisive. improvements [], new [], flaky-pass [], regressions []. GATE PASSED, exit 0. `git diff --stat evals/baselines/` empty.

## Plan 04
Landed (service_type relaxation kept).

## ROADMAP Phase 4 success criteria
1. Editing rules/questions/disqualify text changes behaviour: plan 02 tests.
2. Synonyms and non-business words from the pack: plan 02 tests.
3. Zero differences over the grid: frozen digests, test_frozen_digest_new (plan 05).
4. Roofing eval matches baseline after deletion: gate above.

## Deviations
None beyond the superseded-test deletions listed above.
