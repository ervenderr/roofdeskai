---
phase: 09-docs-pii-retention-and-make-new-business
plan: 05
subsystem: docs
tags: [gen-docs, ops-02, ops-07]
requires: [09-04]
provides: [scripts.gen_docs (render_all, render_readme, scorecard_block, catalog_block, write_docs, main), make gen-docs, docs/generated/]
key-files:
  created: [scripts/gen_docs.py, scripts/doc_templates/sop.md.tpl, scripts/doc_templates/runbook.md.tpl, api/app/test_gen_docs.py, docs/generated/]
  modified: [README.md, Makefile]
requirements-completed: [OPS-02, OPS-07]
---

# Phase 9 Plan 05: Generated docs Summary

Deterministic generator (string.Template.substitute, sorted, no timestamps/env/hash) producing 10 SOPs plus a runbook per pack, a README per-business scorecard and workflow catalog between markers, and drift tests.

## Commits
- 6823cd2 feat: gen_docs SOP and runbook renderer
- (task 2) docs: generated SOPs, runbooks, README scorecard and catalog

## D-09 deviation
The scorecard reads committed `evals/baselines` JSON (via `evals.runner.default_baseline_path(slug)` per pack) instead of `evals/reports`, because the reports are dirty or partial working-tree files and nondeterministic. Result: summit-roofing 94/96, bright-smile-dental 43/43; module rows are case counts only.

## Verification
- RED seen for both tasks (ImportError, then AttributeError/drift failures).
- `make gen-docs` run twice: second run no diff. `make g-test`: 1205 passed. `make check-shared`: OK, 11 allowlisted files. `git status --short businesses prompts` empty.

## Deviations from Plan
- [Rule 3] Makefile `gen-docs` target was missing and was added in task 2 as planned; first sed edit on gen_docs.py failed (BSD sed) and was redone in Python.
- Catalog "tenant-aware" is derived from X-API-Key on API-bound HTTP nodes, not from the hand-maintained UNTENANTED set.

## Not verified
- Generated docs were not reviewed for prose quality beyond tests; the Swiss emergency note (144) is a needs-review flag only.
- Modules line counts top-level entries in cases.yaml; not run results.

## Self-Check: PASSED
