---
phase: 07-engine-modules-and-connectors
plan: 01
subsystem: pack-loader
tags: [pack, pydantic, fixtures, hash-pin]
requires: []
provides: [OPTIONAL_FILES/_parse_optional, Money/Percent/HHMM, load_pack(base=), demo-venue fixture core, packs_dir/venue_tenant/roofing_tenant fixtures]
affects: [07-02..07-08]
key-files:
  created: [api/app/engine/__init__.py, api/app/test_pack_modules.py, api/app/tests_data/packs/demo-venue/*.yaml (6)]
  modified: [api/app/pack.py, api/app/conftest.py]
requirements-completed: [MOD-01]
metrics: {tasks: 2, commit: c82900b}
---

# Phase 7 Plan 01: Pack mechanism and fixture core Summary

Optional-pack-file loader, exact Money/Percent/HHMM validators, `load_pack(slug, base=)`, a synthetic Europe/Zurich `demo-venue` core pack, and sha256 pins that keep roofing and dental byte-identical.

## Commits
- c82900b `feat: pack optional-file mechanism and demo-venue fixture core` (tests and implementation in one commit; the RED run was done before implementing)

## What was done
- RED: `make g-test ARGS="app/test_pack_modules.py -q"` failed at collection with `ImportError: cannot import name 'HHMM' from 'app.pack'`.
- Pinned hashes captured from the unmodified packs: summit-roofing `ead72d1bc518723cc15b50065ba26af34f5294ded89622a0c6386eaca3fedded`, bright-smile-dental `8431b23718c15834fd5596c4a7e99dcb8ab634bc098afadc073ce1dbfe71cb13`. The test comment says deliberate pack edits need a deliberate pin update and that stray files (e.g. .DS_Store) under businesses/ change the hash.
- `OPTIONAL_FILES` is empty. `load_pack` parses optional files for validation but does not yet attach them to `Pack` (plans 03-05 add the fields and the `is None` assertions for roofing/dental).
- Extra fixtures (requested): `packs_dir` (tmp businesses_dir with copied summit-roofing, without scenarios, and demo-venue, monkeypatching `settings.businesses_dir`), `venue_tenant`, `roofing_tenant` (ensure_tenant) in `api/app/conftest.py`. Plan 07-02 also lists conftest.py, so it should expect these already exist.

## Verification (real output)
- `make g-test ARGS="app/test_pack_modules.py app/test_pack.py app/test_dental_pack.py app/test_tenants.py -q"`: all dots, no failures (180 tests).
- Full `make g-test`: `639 passed, 1 warning in 14.23s`.
- `git status --short businesses` empty: nothing under businesses/ changed.

## Deviations from Plan
- Added the venue_tenant/roofing_tenant/packs_dir fixtures and one test (orchestrator request).
- Tests and implementation share one commit rather than a separate RED commit.

## Not verified / risks
- The eval was not run (pack files untouched, hashes pinned; the 94/96 gate is for the end of the phase).
- `venue_tenant` calls `ensure_tenant("demo-venue")`, which inserts a tenant row with slug `demo-venue` into the dev DB. conftest cleanup only deletes `test-%` tenants, so this row persists (harmless; plan 07-02 may want cleanup once demo-venue gets data rows).
- Pydantic float/Decimal path: floats are rejected outright, so no reliance on it.

## Self-Check: PASSED
Files exist, commit c82900b present.
