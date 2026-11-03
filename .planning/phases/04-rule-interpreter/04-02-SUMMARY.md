---
phase: 04-rule-interpreter
plan: 02
subsystem: qualification
tags: [interpreter, differential-test]
requires: [04-01]
provides: [api/app/qualify.py, test_qualify_diff helpers (iter_leads, address_corpus, grid_digest, addr_digest)]
key-files:
  created: [api/app/qualify.py, api/app/test_qualify.py, api/app/test_qualify_diff.py]
metrics:
  tests: "421 passed"
---

# Phase 4 Plan 02: Interpreter and differential proof Summary

Pure `qualify.py` (CHECKS dispatch over four rule types) gives zero differences against the old policy functions over 84,720 leads and 10,052 addresses.

## Commits
- bd3fa21 test: qualify unit tests and differential grid against old policy (red)
- 9a162b5 feat: data-driven qualify interpreter proven identical to old policy
- 452d9b0 test: pack edits change qualification and grounding with no code change

## Red run
Both files failed at collection: `ImportError: cannot import name 'qualify' from 'app'`.

## Grid
GRID_COUNT = 84,720 (main tier 65,520 + edge tier 19,200), ADDR_COUNT = 10,052 (52 curated + 10,000 fuzz, seed 20261103). Both pinned by `test_grid_not_shrunk`. Runtime of the grid diff: about 1.2s. Zero diffs for qualification, missing_fields, next_question and address_status.

## Green
`make g-test`: 421 passed. policy.py, agent.py, runner.py untouched.

## Deviations
- First green run failed only `test_grid_not_shrunk` because my hand-written expected count was wrong (63k estimate); the diff itself was clean. Fixed the pinned constants to the real counts; the diff test was not relaxed.
- Task 3 edit tests passed on first run (they exercise 04-01 loader behaviour plus qualify), so there was no red phase for them.

## Known Stubs
None.

## Self-Check: PASSED
