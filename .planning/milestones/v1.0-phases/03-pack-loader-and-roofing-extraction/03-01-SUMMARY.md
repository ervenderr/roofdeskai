---
phase: 03-pack-loader-and-roofing-extraction
plan: 01
subsystem: pack-loader
tags: [pydantic, yaml, golden-test, tenancy]
requires: [tenants.pack_slug]
provides: [app.pack (load_pack, get_pack, pack_hash, CLI), businesses/summit-roofing, app.tests_data.frozen_old]
affects: [03-02, 03-03]
key-files:
  created: [api/app/pack.py, api/app/test_pack.py, api/app/tests_data/frozen_old.py, businesses/summit-roofing/*.yaml]
  modified: [api/app/config.py, api/app/conftest.py, docker-compose.yml, Dockerfile, api/requirements.txt]
metrics:
  completed: 2026-11-03
---

# Phase 3 Plan 01: Pack loader and roofing extraction (3a) Summary

Frozen Pydantic pack loader (`app/pack.py`) plus the `summit-roofing` pack, proven equal to the old constants by golden tests against both live objects and frozen literals. No call site rewired; no product module, prompt or old constant edited.

## Commits
- 50fe947 chore: freeze roofing constants and add businesses mount/setting
- 24668d7 feat: pack loader with validated models and malformed-pack tests
- e60fe16 feat: roofing business pack with golden tests against live and frozen constants
- fa80f28 chore: pin tzdata 2026.6 (verified on PyPI)

## Notes
- Frozen literals were generated from the live objects in the container before any edit (`tests_data/frozen_old.py`, 20 `FROZEN_*` names incl. both prompt bodies).
- `get_pack` reads `tenants.pack_slug` via `db.system()`; NULL or unknown slug raises `PackError`.
- Cross-file checks (slug == folder, qualifying_services subset of service_synonyms) live in `load_pack` so errors name the file.
- Tests: 30 in `test_pack.py`; full `make g-test`: 295 passed.

## Deploy requirement (flag)
Root `Dockerfile` now has `COPY businesses businesses`. Any Railway deploy of this branch REQUIRES it (and the pack files); not deployed.

## tzdata decision
Pinned `tzdata==2026.6`: PyPI JSON `info.version` 2026.6, present in `releases`, project URL github.com/python/tzdata. Installed in the rebuilt container (`pip show` confirms).

## Requirement deviations
- (a) Roofing `calendar.yaml` timezone is `Etc/UTC`, not `America/Denver` as D-11 lists: legacy slot hours are UTC wall-clock and Denver would shift every slot and break the byte-identical gate. `pack.yaml` keeps `America/Denver` as business identity.
- (b) The demo disclaimer stays core with only the business name from the pack (D-10), so ROADMAP criterion 3 "disclaimer from pack templates" is met only to that extent.

## Deviations from Plan
None otherwise. Note: `test_golden_live` imports old constants and must be deleted in plan 03-03 when they are removed.

## Self-Check: PASSED
Files and commits above verified present; `git diff` on prompts/policy/agent/tools/faq/admin is empty.
