# Eval report (2026-11-04)

- Git SHA: `a405269`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **33/33** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 6/6 / 6/6 |
| Schema validity (first try) | 93% over 56 LLM calls |
| Turn latency p50 / p95 | 9.0s / 17.0s |
| Tokens (prompt / completion) | 37804 / 3284 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 3/3 (100%) |
| escalation | 5/5 (100%) |
| faq | 4/4 (100%) |
| injection | 3/3 (100%) |
| out_of_knowledge | 4/4 (100%) |
| out_of_order | 2/2 (100%) |
| qualified | 4/4 (100%) |
| slots | 3/3 (100%) |
| vague | 2/2 (100%) |
| voice | 3/3 (100%) |

Gates: min category 100%, escalation recall 6/6

## Failures

