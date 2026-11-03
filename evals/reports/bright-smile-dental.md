# Eval report (2026-11-03)

- Git SHA: `de50a6e`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **43/43** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 9/10 / 9/9 |
| Schema validity (first try) | 95% over 78 LLM calls |
| Turn latency p50 / p95 | 6.3s / 9.1s |
| Tokens (prompt / completion) | 56335 / 5004 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 4/4 (100%) |
| escalation | 8/8 (100%) |
| faq | 5/5 (100%) |
| injection | 4/4 (100%) |
| out_of_knowledge | 4/4 (100%) |
| out_of_order | 3/3 (100%) |
| qualified | 4/4 (100%) |
| slots | 4/4 (100%) |
| vague | 3/3 (100%) |
| voice | 4/4 (100%) |

Gates: min category 100%, escalation recall 9/9

## Failures

