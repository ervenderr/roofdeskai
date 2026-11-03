---
phase: 05-per-pack-eval-runner-and-dental-pack
plan: 04
subsystem: tests
tags: [isolation, tenancy, dental]
requires: [05-03]
key-files:
  created: [api/app/test_isolation.py]
requirements: [EVAL-04]
metrics:
  completed: 2026-11-04
---

# Phase 5 Plan 04: Two-tenant isolation tests Summary

9 deterministic pytest tests (no model, hash embedding) prove zero roofing/dental leakage: retrieval (vector and keyword, incl. verbatim cross queries), same-instant booking, cross-tenant slot booking, Europe/Zurich slot generation, conversation ownership, and an interleaved roofing/dental/roofing/dental conversation with per-row tenant checks and prompt/reply assertions.

## Verification
- `make g-test ARGS="app/test_isolation.py -q"`: 9 passed.
- Mutation check (temporary, reverted): removing the tenant filter from `lookup_faq` makes `test_lookup_faq_never_crosses` fail with the other tenant's chunks (TWINT/parking) returned; removing it from the booking UPDATE makes `test_cannot_book_other_tenants_slot` and the interleaved test fail.
- `make g-test` twice: 497 passed both runs. Afterwards 0 `test-%` tenants, 0 rows for non-default tenants, real `bright-smile-dental` tenant never created or touched. No eval run.

## Deviations from Plan
- Both tenants are fresh `test-roofing-<hex>` / `test-dental-<hex>` per test, not the default tenant: reseeding the default tenant's FAQ with hash embeddings would corrupt the dev roofing vectors, and agent_events is append-only so rows cannot be reset between tests. Cleanup is conftest's existing `test-%` sweep.
- Prompt isolation: the shared `prompts/agent.v2.md` contains a static extraction example mentioning "Denver" and `repair`, so dental prompts contain "Denver". This is template text identical for every tenant, not tenant data (known risk in 05-RESEARCH section 7); the test asserts the count equals the template's own count and that no Summit Roofing name or roofing FAQ text appears. Not changed, to avoid moving the roofing 94/96 gate. Possible Phase 9 cleanup: make the example a pack token.

## Findings
No real cross-tenant leak found.

## Known Stubs
None.

## Self-Check: PASSED
