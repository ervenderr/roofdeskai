# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-03)

**Core value:** Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.
**Current focus:** Phase 1: Baseline Freeze and Environment Isolation

## Current Position

Phase: 1 of 10 (Baseline Freeze and Environment Isolation)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-11-03 - Roadmap created

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: -

**By Phase:** none yet

## Accumulated Context

### Decisions

- Roadmap follows research's 10-phase order unchanged.
- EVAL-02 (roofing 94/96) is a cross-cutting gate, assigned to Phase 5 as its final checkpoint; BASE-04 enforces it per step from Phase 1.
- EVAL-05 sits with the engine modules (Phase 7); EVAL-06 with the held-out run (Phase 10).

### Pending Todos

None yet.

### Blockers/Concerns

- Which DB role the app uses today (owner means RLS will not enforce) - resolve in Phase 2.
- Deploy branch: repo is `master`, spec says `main` - confirm.
- Read `intake.py`, `prompts/`, `api/app/llm.py` `_call` before the phases that touch them.
- Dental health-data and cross-border LLM handling: decide Phase 5, document Phase 9; demo uses synthetic data.
- Phases flagged for deeper research: 2, 4, 7, 8, 9.

## Session Continuity

Last session: 2026-11-03
Stopped at: Roadmap created
Resume file: None
