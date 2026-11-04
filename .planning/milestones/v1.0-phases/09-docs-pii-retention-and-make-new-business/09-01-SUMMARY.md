---
phase: 09-docs-pii-retention-and-make-new-business
plan: 01
subsystem: logging
tags: [pii, logging, ops-03]
requires: []
provides: [mask(), PiiMaskFilter, install_log_filters]
affects: [api/app/main.py]
key-files:
  created: [api/app/engine/mask.py, api/app/test_pii_mask.py]
  modified: [api/app/logctx.py, api/app/main.py]
requirements-completed: [OPS-03]
---

# Phase 9 Plan 01: PII mask and log filter Summary

Pure `mask()` (email and phone, UUID/date/IPv4 protected) plus `PiiMaskFilter` installed on root and uvicorn handlers; args shape preserved so uvicorn AccessFormatter works.

## Commits
- 39c3f13 feat: pii mask() for log lines
- 55db469 feat: mask email and phone in all log handlers

## Verification
- RED seen for both tasks (collection ImportError before implementation).
- `make g-test`: 1133 passed. `git status --short businesses prompts` empty.

## Deviations from Plan
- `test_logging_tenant.py` was not modified (listed in files_modified); existing tests passed unchanged and install is covered in `test_pii_mask.py`.
- `install_log_filters()` also installs TenantFilter on root handlers (same behaviour as before, moved into the helper).

## Not verified
- Live uvicorn access-log output in a running server (covered by an AccessFormatter unit test only).
- A separator-less 10-digit phone is not masked (documented `shortcut:` in mask.py).
- n8n execution data and Mailpit are not covered by this filter.

## Self-Check: PASSED
