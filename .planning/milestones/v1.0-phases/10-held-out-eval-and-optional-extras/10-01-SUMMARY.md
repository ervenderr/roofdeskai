---
phase: 10-held-out-eval-and-optional-extras
plan: 01
requirements: [EVAL-06]
key-files:
  created: [api/app/test_heldout.py, evals/heldout/summit-roofing/*.yaml, evals/heldout/bright-smile-dental/*.yaml]
  modified: [evals/runner.py, Makefile]
---

# Phase 10 Plan 01: Held-out scenarios and --heldout tooling Summary

20 held-out scenarios (12 roofing `ho-r-*`, 8 dental `ho-d-*`) plus a slug-agnostic `--heldout` runner mode with a run-once guard, committed together. Nothing was run against the model.

## Scenarios SHA (frozen, D-01)

**6fc701f** (`git log -1 --format=%h -- evals/heldout`). Commit message: `test: add 20 held-out eval scenarios and --heldout runner mode`. No scenario edits allowed after this commit.

## What was built

- `load_scenarios(slug, root=None)`, `run_heldout`, `--heldout` / `--force-rerun REASON`, `write_report(out=, header=)`, `HELDOUT` and `REPORTS` constants in `evals/runner.py`.
- `make g-heldout PACK=<slug> [PRECHECK=text]` refuses on dirty `evals/heldout` (excluding results/) or dirty shared code; passes GIT_SHA, HELDOUT_SHA, HELDOUT_PRECHECK.
- Run aborts (no record, no report) on non-local model or any infra fault (`r None` / `error:`).
- `api/app/test_heldout.py`: 18 tests (loader root, parsing rejects, guard, abort paths, set counts/prefix/disjointness).

## Verification

- RED confirmed first (7 failed, 5 errors); GREEN afterwards.
- `make g-test`: 1225 passed. `make check-shared`: OK, runner still at 19 allowlisted hits.
- `git status --short businesses prompts` empty; `evals/heldout/results` does not exist.

## Deviations

None from the plan. Minor: SHAs come only from env (`GIT_SHA`, `HELDOUT_SHA`), never `_git_sha()`, as the plan required.

## Unverified

- `make g-heldout` was only dry-run (`make -n`); the container exec path and the real write_report with `out=` were not executed (no eval allowed). Guard tests use a faked write_report.
- Scenario expectations (e.g. escalation regex coverage of ho-r-10 / ho-d-06, FAQ require patterns) were deliberately not checked against the pack; failures stand per D-01.
- ho-d-07 reuses the "steal slot" mechanism of the dev slots category (content differs).
