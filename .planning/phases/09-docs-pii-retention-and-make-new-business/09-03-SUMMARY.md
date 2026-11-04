---
phase: 09-docs-pii-retention-and-make-new-business
plan: 03
subsystem: ops-gate
tags: [grep-gate, ops-06]
requires: [09-02]
provides: [check_shared.find_hits, check_shared.check, ALLOW, make check-shared]
key-files:
  created: [scripts/check_shared.py, api/app/test_shared_gate.py]
  modified: [api/app/triage.py, api/app/engine/reviews.py, Makefile, docker-compose.global.yml]
requirements-completed: [OPS-06]
---

# Phase 9 Plan 03: Grep gate Summary

Gate for roofing words in shared code with per-file pinned hit counts (11 allowlisted files), two comment-only rewordings, branch-only compose mounts, and `make check-shared`.

## Commits
- 0dfb3a8 feat: grep gate for roofing words in shared code
- dc35589 chore: reword roofing comments in shared code, add check-shared target and branch mounts
- (next) fix: ignore /srv/api mount in g-test so conftest is not collected twice

## Verification
- RED seen (ImportError) then 7 unit tests green; `ls /srv/api /srv/docs /srv/dashboard /srv/README.md` listed contents in the container.
- `make check-shared`: "check-shared OK: 11 allowlisted files, no other hits".
- Full `make g-test`: 1171 passed. `git status --short businesses prompts` empty.

## Deviations from Plan
- [Rule 3] The `./api:/srv/api` mount made a bare `pytest` collect `/srv/api/app/conftest.py` a second time (ValueError). Makefile `g-test` now passes `--ignore=api`.
- Real hit counts differ from research: config.py 4, outreach.py 2 (not reworded, allowlisted), outreach-flow.json 16, evals/runner.py 19, seed_demo.py 12, prompts v1 files 4 each, page.tsx 2. Pins use the run counts.
- Hit scan used `.py .json .md .yaml .yml .ts .tsx .js .mjs .sh .txt .css .tpl` only.

## Not verified
- Dashboard mounts exclude node_modules/.next by mounting only app/components/lib.
- Later plans adding files under scripts/ or api/app must stay word-free or extend ALLOW.

## Self-Check: PASSED
