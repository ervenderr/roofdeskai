---
phase: 01-baseline-freeze-and-environment-isolation
plan: 01
subsystem: infra
tags: [docker-compose, git-tag, inventory]
requires: []
provides:
  - local tag v1-roofing at 27a2785
  - isolated compose project roofdesk-global (ports 55432, 18025, 11025, 15679, 18081)
  - g-up/g-down/g-reset/g-logs/g-eval make targets
  - 01-ROOFING-INVENTORY.md
key-files:
  created: [docker-compose.global.yml, .planning/phases/01-baseline-freeze-and-environment-isolation/01-ROOFING-INVENTORY.md]
  modified: [Makefile]
requirements-completed: [BASE-01, BASE-03]
completed: 2026-11-03
---

# Phase 1 Plan 01: Baseline tag, isolated stack, roofing inventory

Tagged untouched roofing at `v1-roofing` (27a2785, not pushed), added a `roofdesk-global` compose project with remapped host ports via `!override`, and wrote the roofing assumption inventory.

## Tasks

| Task | Result | Commit |
|------|--------|--------|
| 1 Tag v1-roofing | Code-diff check since 5c214ce printed nothing; tag == HEAD (27a2785) | git ref only |
| 2 Isolated compose + Makefile | `config` shows published 55432, 18025, 11025, 15679, 18081; `make g-up` ran; volumes `roofdesk-global_pgdata`, `roofdesk-global_n8ndata` exist; containers `roofdesk-global-{db,api,n8n,mailpit}-1` up | bc06712 |
| 3 Inventory | 30-row table incl. intake.py, policy.py, agent.v2.md, db seeds | 5b8d746 |

## Verification
- `git diff` on docker-compose.yml, docker-compose.override.yml, .env: empty.
- `docker ps` after `make g-up`: db 55432->5432, mailpit 18025/11025, n8n 15679->5678, api unexposed. No live stack was running, so side-by-side collision was not exercised.

## Deviations
None. Note: the plan's automated grep expects 4 published ports; the scraper (profile-gated) adds a 5th (18081) only with `--profile scraper`.

## Notes
- The branch stack is left running (`make g-down` to stop). Healthchecks were not waited on beyond db being Healthy; the api/n8n startup was not tested.
- Inventory line numbers are from grep, not hand-reviewed per row; policy.py qualification-constants row has no single line number.
- Commits are plain `<type>: <desc>` per user rules.
