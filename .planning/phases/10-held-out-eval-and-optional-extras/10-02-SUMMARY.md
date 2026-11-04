---
phase: 10-held-out-eval-and-optional-extras
plan: 02
requirements: [EVAL-06]
---

# Phase 10 Plan 02: Held-out run and publication Summary

Held-out score **17/20** (roofing 10/12, dental 7/8), one run per pack on local llama3.1:8b, local_only true, reruns empty.

## SHAs
Scenarios `6fc701f`; run `01f0fd9`. Precheck `git diff --quiet 6fc701f HEAD -- api prompts businesses scripts evals/runner.py` exit 0 stored in both records.

## Runs
- `make g-heldout PACK=summit-roofing`: exit 0, 10/12. Failed: ho-r-01, ho-r-02 (qualified; state COLLECT != DONE, no book_appointment call).
- `make g-heldout PACK=bright-smile-dental`: exit 0, 7/8. Failed: ho-d-08 (voice; same booking failure).
- First roofing attempt exited 2 at the make guard (untracked scripts/check-and-deploy.sh). No eval ran, no record written, so not a re-run.

## Commits
24c194c `docs: publish held-out eval score` (records, reports, docs/heldout-eval.md, README); ae7e4a7 `test: drop pre-run results-dir sentinel after held-out run`.

## Deviations
- Moved the unrelated untracked scripts/check-and-deploy.sh out of the tree for each run (guard refuses untracked files under scripts/), restored afterwards. Disclosed in docs/heldout-eval.md.
- Held-out score is README prose outside the generated markers, not in the generated scorecard (deviates from D-01 wording; gen-docs not extended; `make gen-docs` not run).
- Removed `test_zz_real_results_dir_untouched` from api/app/test_heldout.py: it asserted the results dir does not exist and necessarily fails once records exist. Post-run, test-only.
- Plan said background runs; the dental run and roofing run were both executed in background, one at a time, no pytest concurrent.

## Verification
Targeted tests 37 passed; `make check-shared` OK; full `make g-test` 1224 passed; businesses/prompts/heldout scenario dirs clean.

## Unverified
- Roofing 94/96 and dental gates not re-run in this plan.
- Failure causes not investigated (reported only, per D-01).
