# Milestones

## v1.0 RoofDesk Global (Shipped: 2026-11-04)

**Phases completed:** 10 phases, 57 plans, 7 tasks

**Key accomplishments:**

- Multi-tenant core: numbered migrations, `db.tx(tenant_id)`, FORCE RLS with non-owner role, per-tenant hashed API keys
- Business packs: roofing extracted as pack #1 (byte-identical prompts), data-driven qualification interpreter, dental pack 43/43, venue pack 33/33
- Roofing regression gate held at 94/96 (same two voice failures) through every step
- Engine modules: quote builder, capacity checker, connectors (mock), daily brief, review responder, intake_event
- 10 tenant-aware n8n workflows plus API-only operation (`run_flows.py`) and header CI check
- Ops: `make new-business`, PII log masking, retention/delete_subject, generated SOPs/runbooks, grep gate, data map
- Held-out eval published at 17/20; optional Anthropic provider (not yet run) and MCP connectors

Known deferred items at close: 4 human_needed verifications (phases 5, 6, 8, 9) plus tech debt listed in milestones/v1.0-MILESTONE-AUDIT.md

---
