---
phase: 03-pack-loader-and-roofing-extraction
verified: 2026-11-03T00:00:00Z
status: passed
score: 5/5 success criteria verified (criterion 3 partly met by design D-10, accepted)
---

# Phase 3: Pack Loader and Roofing Extraction Verification Report

**Goal:** Summit Roofing is a pack folder, and the agent reads business values from the pack instead of code.
**Status:** passed (with two accepted deviations, see below)

## Evidence

- `make g-test` (branch stack, run by verifier): `389 passed, 1 warning in 6.92s`.
- Gate: scratchpad `gate.log` ends `improvements: [] / new: [] / flaky-pass: [] / regressions: [] / GATE PASSED / EXIT=0`. `evals/reports/latest.md`: 94/96, Models: local:llama3.1:8b only, failures `voice-over-explainer` and `voice-indecisive` (the baseline pair). Report SHA `58d4264`; the only change since is `03-05-SUMMARY.md` (docs), so the code gated is the code at HEAD. The eval gate was not re-run by the verifier.

## Success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Malformed pack fails at load naming file and field | VERIFIED | `api/app/pack.py`: `M` forbids extras; `_parse` raises `PackError(f"{path}: {loc}: {msg}")`; also missing file, bad YAML, slug mismatch, qualifying-not-in-synonyms. `test_pack.py::test_malformed*`, `test_cli_fail`, `python -m app.pack <slug>` CLI exists. All pass. |
| 2 | Golden test: pack values equal old constants | VERIFIED | `api/app/tests_data/frozen_old.py` fixtures; `test_golden_frozen`, `test_golden_always_human_matches_client_profile`, `test_templates_exact`, `test_faq_seed_sql_matches_pack`. Pass. |
| 3 | Prompt byte-identical; replies, confirmation email, demo disclaimer from pack | VERIFIED (disclaimer partly, by design) | `test_render_agent/faq/full_message`, `test_render_prompt_version_headers`, `test_messages_*` pass; `agent.py::_notify_booking` uses `pack.messages` for owner alert and customer subject/intro. Disclaimer: `agent.py:23 DEMO_NOTICE` stays core code; only `{business}` comes from `pack.meta.business` (decision D-10). |
| 4 | Pack calendar edits change slot generation | VERIFIED | `tools.slot_instants(pack.calendar, now)`; `test_slots_equivalence` (vs old), `test_slots_pack_edits`, `test_slots_timezone_shift`, `test_slots_buffer_drops_starts`, `test_ensure_slots_live`. |
| 5 | Eval matches baseline per scenario; no module-level business global | VERIFIED | Gate passed, regressions `[]`. Grep for `summit\|roof(?!desk)\|denver` over `api/app/*.py` (non-test) leaves only: `config.py` default tenant comment and `client_profile` selector (a pointer to the pack, not a value), `replies.py:47` and `prospects.py` / `outreach.py` (outbound prospecting copy about RoofDesk, outside agent/pack scope), `triage.py:64` (reads from pack). `test_no_globals` passes. |

## Requirements

| Req | Status | Evidence |
|-----|--------|----------|
| PACK-01 | SATISFIED | `businesses/summit-roofing/{pack,calendar,escalation,faq,messages,qualification}.yaml`; Pydantic `extra="forbid"` models; `PackError` messages; malformed tests. |
| PACK-02 | SATISFIED | Golden tests above; `policy.py`, `faq.py`, `agent.py`, `tools.py`, `triage.py` take values from `get_pack`. |
| PACK-03 | SATISFIED | `render()` with unresolved-placeholder error; byte-identical render tests; `prompts/` mounted (`docker-compose.yml:42`) and `COPY prompts prompts` in root `Dockerfile:7`. |
| PACK-04 | SATISFIED with deviation | Reply strings, owner alert, customer email from `messages.yaml`. Disclaimer text in core (see D2). |
| PACK-05 | SATISFIED | Calendar from `calendar.yaml`; tests above. Timezone deviation D1. |
| PACK-06 | SATISFIED | `escalation.yaml` holds roofing safety regex; `test_escalation_equivalence`, `test_escalation_without_pack_has_no_safety` (generic defaults stay in code). |
| PACK-07 | SATISFIED | `_CACHE` keyed `(tenant_id, pack_hash)`, old key evicted on reload; `test_cache_interleaved_tenants_and_reload`; `test_no_globals`. `businesses` mounted (`docker-compose.yml:44`) and `COPY businesses businesses` (`Dockerfile:9`). |

No orphaned requirements. No TBD/FIXME/XXX debt markers found in the files checked.

## Deviations assessed

- **D1, roofing calendar `timezone: Etc/UTC` while `pack.yaml` says America/Denver.** Acceptable. Legacy v1 slots were UTC wall-clock; switching would move every slot 6-7h and break the zero-behaviour-change gate. The loader honours a different tz (`test_slots_timezone_shift`), and `calendar.yaml` documents why. Follow-up: flip to America/Denver as a deliberate, separate behaviour change (a later phase or the Denver go-live), with live slots regenerated. Not a Phase 3 blocker.
- **D2, demo disclaimer stays core (D-10).** Acceptable gap, partly meets PACK-04 / criterion 3 by design. The disclaimer is RoofDesk platform text (it says "demo of RoofDesk AI"), not business-specific, and the business name inside it is pack-driven. Risk: a real (non-demo) tenant would still get the demo notice. Follow-up recommended, not blocking: make it an optional `messages.demo_notice` pack field (or tenant flag) before any non-demo tenant goes live; fits Phase 9 (docs / make new-business) or Phase 5 (dental pack). Consider amending the ROADMAP/REQUIREMENTS wording so the contract matches D-10.

## Gaps

None blocking.

_Verified: 2026-11-03_
_Verifier: Claude (gsd-verifier)_
