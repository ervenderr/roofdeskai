---
phase: 05-per-pack-eval-runner-and-dental-pack
plan: 05
subsystem: evals
tags: [eval, dental, tuning, baseline]
requires: [05-04]
key-files:
  created: [evals/baselines/bright-smile-dental.json, evals/reports/bright-smile-dental.md]
  modified: [businesses/bright-smile-dental/faq.yaml]
requirements: [EVAL-03]
metrics:
  completed: 2026-11-04
---

# Phase 5 Plan 05: Dental eval run, tuning and baseline Summary

EVAL-03 met: bright-smile-dental scores 43/43 on local llama3.1:8b (all categories 100%, emergency recall 9/9) after 2 tuning iterations that changed only `faq.yaml`; baseline committed.

## Per-category results (all runs: Models = local:llama3.1:8b only, temperature 0)

| Category | Iter 0 (b0d612d) | Iter 1 (8172631) | Iter 2 (de50a6e) | Baseline run (de50a6e) |
|---|---|---|---|---|
| disqualified | 2/4 (50%) | 4/4 | 4/4 | 4/4 |
| escalation | 8/8 | 8/8 | 8/8 | 8/8 |
| faq | 5/5 | 5/5 | 5/5 | 5/5 |
| injection | 4/4 | 4/4 | 4/4 | 4/4 |
| out_of_knowledge | 4/4 | 4/4 | 4/4 | 4/4 |
| out_of_order | 3/3 | 3/3 | 3/3 | 3/3 |
| qualified | 4/4 | 4/4 | 4/4 | 4/4 |
| slots | 1/4 (25%) | 3/4 (75%) | 4/4 | 4/4 |
| vague | 3/3 | 3/3 | 3/3 | 3/3 |
| voice | 4/4 | 4/4 | 4/4 | 4/4 |
| Overall | 38/43 | 42/43 | 43/43 | 43/43 |
| Gates line | min 25%, recall 9/9 | min 75%, recall 9/9 | min 100%, recall 9/9 | min 100%, recall 9/9 |

## Diagnosis and tuning
- Iter 0 failures (ddisq-implants, ddisq-braces, dslot-taken, dslot-weekend, dslot-question): from replaying the scenarios with raw model output, on turn 1 the model put the requested service into `name` ("Cleaning", "Checkup please") and omitted `service_type`, or returned empty extraction for implants/braces instead of `"other"`. The code then re-asked the service question, so the scenarios never progressed.
- Iter 1 (8172631): `faq.yaml` services and not_offered entries state that a requested treatment is `service_type` (or `"other"` for unoffered ones), not a name. 5 failures -> 1.
- Iter 2 (de50a6e): same hint added to the location entry, which is the chunk retrieved for "<service> please, I live at <address>" messages (dslot-taken). 1 failure -> 0.
- No scenario, api/ code, prompt, or other file changed (`git diff` on scenarios/, api/, v1-roofing.json empty).

## Findings
- The 'Denver' roofing example in `prompts/agent.v2.md` did not show up in any dental reply or extraction in the traced runs; not edited.
- The tuning works by writing extraction guidance into FAQ text, which is retrieval-dependent; a message whose top-3 chunks include none of the hinted entries can still hit the original model behaviour. A durable fix is a prompt/engine change (out of scope here), e.g. a pack-level extraction hint in the prompt template.
- One `make g-test` run immediately after the baseline commit exited 1 (output was truncated and not captured); three consecutive reruns were 497 passed. Cause not identified; possibly leftover state from the eval just before. Flagging, not investigated.

## Commits
- 8172631 fix: tune dental pack iteration 1
- de50a6e fix: tune dental pack iteration 2
- 65a34fd test: add bright-smile-dental baseline

## Deviations from Plan
None, apart from offline replay probes of the failing scenarios (via the runner's `run_scenario`) before each full run; these were diagnostic, not counted as iterations.

## Known Stubs
None.

## Self-Check: PASSED
