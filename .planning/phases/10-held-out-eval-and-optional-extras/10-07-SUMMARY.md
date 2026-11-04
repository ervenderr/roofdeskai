---
phase: 10-held-out-eval-and-optional-extras
plan: 07
subsystem: verification
tags: [gates, regression, heldout, mcp, anthropic]
requirements-completed: [EVAL-06, EXT-01, EXT-02, EXT-03]
completed: 2026-11-04
---

# Phase 10 Plan 07: Final serial gates Summary

All gates green, run strictly serially at HEAD 701b1bc on the branch stack (llama3.1:8b warmed first, `LLM_TIMEOUT_S=240`). No code or pack changes in this plan.

## Gate results

| # | Gate | Result | Exit |
|---|------|--------|------|
| 1 | `make g-test` | 1277 passed | 0 |
| 2 | `make check-n8n` | 31 passed | 0 |
| 3 | `make check-shared` | OK, 11 allowlisted files, no other hits | 0 |
| 4 | `make gen-docs` drift (`git diff --stat docs/generated README.md`) | empty (after remount, see deviations) | 0 |
| 5 | Roofing `--gate` | **94/96**, failures exactly voice-over-explainer and voice-indecisive; no regressions, no improvements | 0 |
| 6 | Dental `--pack bright-smile-dental --gate` | **43/43** | 0 |
| 7 | Puzzle-peak `--pack puzzle-peak --gate` | **33/33**, first run, no rerun needed; all categories 100%, escalation 6/6 recall 6/6, booking validity 100% | 0 |
| 8 | `make g-eval-modules` | quote 33/33, capacity 16/16, brief 16/16, reviews 45/45, intake 19/19 | 0 |
| 9 | `new-business` summit-roofing / bright-smile-dental / puzzle-peak (smoke OK 8 scenarios, cross-tenant OK) | all pass | 0 / 0 / 0 |

No eval run fell back to a hosted model (log grep for timeout/fallback: 0 hits in roofing and dental; puzzle-peak run local, passed). No reruns were needed.

## Integrity checks

- `git status` and `git diff 985199e HEAD` for `businesses/summit-roofing`, `businesses/bright-smile-dental`, `prompts`: empty.
- `git diff 6fc701f HEAD -- evals/heldout/summit-roofing evals/heldout/bright-smile-dental`: empty.
- `_heldout_sha256()` recomputed in the api container = `471917ee...45a5`, equal to `scenarios_sha256` in both held-out records. Both records have `reruns: []` (exactly one run per pack).
- `git status evals/baselines`: no change. Gate runs rewrote `evals/reports/{latest,puzzle-peak,bright-smile-dental}.md`; not staged.

## Figures

- Held-out (run SHA 01f0fd9, scenarios SHA 6fc701f): **17/20**, roofing 10/12, dental 7/8. Three booking scenarios failed and were not fixed. Authored by the same assistant with dev sets visible: held out from tuning, not independent. README prose matches the records, so no README edit or commit was needed.
- Venue (puzzle-peak) per category at this gate: disqualified 3/3, escalation 5/5, faq 4/4, injection 3/3, out_of_knowledge 4/4, out_of_order 2/2, qualified 4/4, slots 3/3, vague 2/2, voice 3/3 (all 100%), escalation recall 100%. No shortfall this run. Its disqualified scenarios are known to be flaky on the local 8B; they passed this time.
- Anthropic (EXT-01): implemented and tested with fake clients only. No real Anthropic call was made. The real scorecard remains a user action (needs key and cost approval): `make g-eval ARGS="--pack <slug> --providers anthropic"`.
- MCP (EXT-02): `python -m scripts.mcp_server` over stdio, tools `fetch_sheet`, `fetch_accounting`, `fetch_bookings`, `fetch_ads` (tenant, day), mock-labelled.

## Deviations

1. **[Rule 3 - Blocking] Stale README bind mount.** First `make gen-docs` truncated README.md. The api container saw README.md at 22884 bytes while the host file was 23548 (the file is a single-file bind mount whose inode had been replaced by earlier host edits, e.g. in 10-06). I restored README.md from HEAD (`git show HEAD:README.md`), restarted the api container to remount it, and re-ran `gen-docs`: drift empty. No source change. Risk: anyone running `make gen-docs` against an un-restarted container after a host-side README edit gets a truncated README; check `git diff README.md` after gen-docs.
2. **Dependency drift.** SQLAlchemy resolved 2.1.6 -> 2.1.8 when the api image was rebuilt in 10-06 (unpinned patch). All gates above ran on 2.1.8 and passed.

## Open items carried

Confirm "call 144" Swiss emergency number; deploy requirements; Co-Authored-By trailers on two Phase 3 commits (local, unpushed); n8n licence decision; Phase 8 `Check key` loop abort (new-business output still warns tenants need a key in TENANT_API_KEYS).

## Self-Check: PASSED
