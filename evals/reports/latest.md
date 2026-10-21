# Eval report (2026-10-21)

- Git SHA: `unknown`  Prompt: `agent.v2`  Models: local:llama3.1:8b
- Overall: **80/80** scenarios passed

| Metric | Value |
|---|---|
| Booking validity (must be 100%) | 100% |
| Escalation precision / recall | 8/8 / 8/8 |
| Schema validity (first try) | 96% over 180 LLM calls |
| Turn latency p50 / p95 | 7.2s / 9.9s |
| Tokens (prompt / completion) | 119872 / 12364 (local = $0) |

| Category | Passed |
|---|---|
| disqualified | 10/10 |
| escalation | 8/8 |
| faq | 10/10 |
| injection | 8/8 |
| out_of_knowledge | 8/8 |
| out_of_order | 8/8 |
| qualified | 12/12 |
| slots | 6/6 |
| vague | 10/10 |

## Failures

