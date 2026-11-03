---
phase: 02-tenants-migrations-and-db-plumbing
plan: 05
subsystem: testing
tags: [rls, migrations, evals]
requires: [02-04]
key-files:
  created: [api/app/test_rls_proof.py]
  modified: [api/app/test_tenancy.py]
requirements-completed: [TEN-01, TEN-02, TEN-03, TEN-04, TEN-05, TEN-06]
completed: 2026-11-03
---

# Phase 2 Plan 05: Proofs and eval gate Summary

RLS pattern, dump-restore migration and call-site gates pass. The full eval gate printed GATE PASSED but is NOT clean evidence of 94/96 on local-only (see below).

- Commits: a7fb555 (RLS proof, 9 tests), 43802db (grep gate, 4 tests).
- RLS proof: non-owner NOSUPERUSER NOBYPASSRLS role + FORCE RLS sees only own tenant, fails closed with no tenant, WITH CHECK rejects cross-tenant insert, transaction-local on a pool of 1, superuser control sees all. Role and scratch DB dropped.
- Finding: after a tx commits, `current_setting('app.tenant_id', true)` returns `''` (not NULL) on the reused connection, so a policy using bare `::uuid` errors instead of failing closed. Phase 6 policies must use `NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
- Migration proof (pre-migration branch-pre.dump restored into scratch leadpilot_mig; empty leadpilot_empty): row counts equal pre/post (leads 682, conversations 682, messages 2339, slots 40, faq_chunks 12); zero NULL tenant_id on all tenant tables, llm_calls NULL count 0; versions 001_tenants..004_agent_events on both; second bootstrap leaves count at 4; schema-only dump diff between mig and empty is only the random pg_dump `\restrict` token lines. pytest on the mig DB: 265 passed. Scratch DBs dropped.
- `make g-test`: 265 passed.

## Eval gate (caveat)
`make eval-gate` exit 0, "GATE PASSED", regressions: []. But the first full pass scored 41/96: local llama3.1:8b hit `APITimeoutError`, the chain fell through to groq (429) and ovh (403), and 55 scenarios errored with "all LLM providers failed or are cooling down" (including voice-over-explainer and voice-indecisive). The 55 were then rerun twice and reported as flaky-pass. The report header lists `Models: groq:openai/gpt-oss-20b, local:llama3.1:8b`. So the gate did not run cleanly local-only, and 94/96 was not demonstrated as a clean pass. The final log does not state a 94/96 score. Recommend rerunning with the groq/ovh keys unset and the local model warmed (timeouts), then confirming. Baseline untouched.

## Deviations
- Dump file in the scratchpad was not deleted (rm was blocked by the permission classifier); scratch DBs and /tmp copy in the db container were not affected beyond that. Delete branch-pre.dump manually if wanted.
- Gate log: scratchpad/gate.log.

## Self-Check: PASSED (proofs); eval gate evidence inconclusive

## Eval gate result (orchestrator follow-up)

The executor's first gate run was not clean: local timeouts cascaded into hosted fallbacks, so the gate (which had no local-only guard) printed PASSED on a contaminated run. Fixed in 96f64cc: `gate` now calls `assert_local_only` over all run and rerun conversations. A second run aborted correctly (groq answered after a local timeout under memory pressure). Third run, `LLM_TIMEOUT_S=300`, model kept warm, no other changes: **94/96, Models: local:llama3.1:8b, failures only voice-over-explainer and voice-indecisive, regressions [], flaky-pass [], GATE PASSED, exit 0** (git sha 96f64cc).

Operational note: on this 16 GB laptop under memory pressure the default 60s LLM timeout can trip; run the gate with `LLM_TIMEOUT_S=300`.
