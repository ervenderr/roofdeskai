---
phase: 05-per-pack-eval-runner-and-dental-pack
verified: 2026-11-04T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
human_verification:
  - test: "Confirm the Swiss emergency number 'call 144' in the fictional dental pack"
    expected: "Owner accepts or corrects the assumed number"
    why_human: "Flagged ASSUMED in 05-06-SUMMARY; factual claim in pack text"
  - test: "Identify the intermittent pytest failure that appears right after an eval run"
    expected: "Failing test id captured and root cause found (leftover DB state suspected)"
    why_human: "Cause unknown; seen twice; reruns pass 497/497. Not run by verifier (instructed not to run pytest)"
---

# Phase 5 Verification

Goal: a second business runs on the same code, scored separately, with no leakage. Verified by reading code, tests, baselines and reports only; no pytest or evals were run.

| Req | Status | Evidence |
|---|---|---|
| EVAL-01 | SATISFIED | `evals/runner.py` has `--pack` (default summit-roofing). Per-slug paths: `default_baseline_path` (roofing `v1-roofing.json`, others `<slug>.json`), `flake_path`, `report_path` (roofing `latest.md`, others `<slug>.md`, partial runs `-partial`). Roofing baseline overwrite is refused without `--force-baseline`. `load_pack(slug)` runs before any DB or path use. Files exist for both packs; `v1-roofing.json` last touched at de64fd9 (pre-phase). `test_eval_gate.py` has per-pack tests, including one that checks pack files are isolated across modes. |
| EVAL-02 | SATISFIED | `evals/reports/latest.md`: 94/96, models `local:llama3.1:8b` only, failures exactly `voice-over-explainer` and `voice-indecisive`. Baseline JSON (96 scenarios, 94 passed) has the same two failures. Gate recorded as passed with regressions []. |
| EVAL-03 | SATISFIED | `businesses/bright-smile-dental/scenarios/*.yaml` holds 43 scenarios across the 10 categories. `test_dental_pack.py` asserts the counts, 43 total and `d`-prefixed ids. `reports/bright-smile-dental.md` shows 43/43, every category 100%, escalation recall 9/9. `bright-smile-dental.json` baseline has 43 scenarios, 43 passed. Flake report shows 0 unstable. Recall is also checked deterministically: `test_emergency_recall_is_total` and `test_scenario_recall_is_deterministic_and_total` (9 emergency scenarios), plus a no-false-escalation test. |
| EVAL-04 | SATISFIED (with note) | `test_isolation.py` has 9 tests: FAQ lookup and keyword fallback never cross, slot and booking isolation, conversation not continuable across tenants, and `test_interleaved_conversations_do_not_cross`. The last asserts per-tenant row counts, no cross-tenant FK mismatches, replies free of the other business's terms, and each prompt naming only its own business and FAQ. Dental scenarios `dinj-other-business` and `dook-roofing` pass in the gate. Note: there are no roofing iso-* eval scenarios (D-13); cross-tenant retrieval is covered by pytest, not by eval scenarios. |

ROADMAP criteria: 1 (per-pack, no overwrite) VERIFIED. 2 (94/96) VERIFIED. 3 (dental ~40, no category under 90%, recall 100%) VERIFIED. 4 (zero leakage) VERIFIED.

## Warnings
- The unexplained intermittent pytest failure after eval runs (twice; 497/497 on rerun) is unresolved. It could hide a state-leak between runs, which matters for a phase about leakage. The failing test id was never captured.
- Dental scenarios were tuned against a local 8B model; FAQ-steering sentences were added to dental `faq.yaml` during tuning (05-05). This is a retrieval-dependent fix, not durable.
- Shared `prompts/agent.v2.md` contains a static "Denver" example, so dental prompts contain "Denver". It is template text, not tenant data, and `test_isolation.py` accounts for it explicitly. Possible Phase 9 cleanup.
- Deviations that were accepted in the summary: D-05 (Mon-Fri instead of Mon-Sat), `forbid_reply_regex` alias, CHF added to the shared unsupported_claim regex, dental runs appearing in the admin eval trend. Known limits: Swiss postcodes and umlauts, spoken house numbers.
- Roofing 94/96 and dental 43/43 are single-model local runs, and LLM output is non-deterministic. The evidence is the recorded runs, not something re-run here.
- Untracked `evals/reports/latest-partial.md` is a stray partial-run artifact.

## Anti-patterns
No TBD, FIXME or XXX scan was run beyond reading the key files. None noticed in `evals/runner.py`.

_Verifier: Claude (gsd-verifier)_
