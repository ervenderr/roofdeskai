# Data map

Where personal data is stored, who processes it, how it is aged out, and what is not covered. Taken from the code (`db/`, `api/app/retention.py`, `api/app/llm.py`, `api/app/engine/mask.py`, `docker-compose.yml`). Statements about law are not made here; items marked "needs review" need a qualified person. `api/app/test_data_map.py` fails if a tenant table is missing from this file.

## Stores

Postgres (pgvector image). Tenant tables have `tenant_id` and row-level security; the app connects as the non-owner role `app_rw`.

| Store | Holds | PII | Retention treatment |
|---|---|---|---|
| leads | name, email, phone, address, job details | yes | purged by age (`created_at`), if no remaining conversation and no future appointment |
| conversations | external_id (contact id), channel, timestamps | possible (external_id) | purged by `COALESCE(ended_at, started_at)` |
| messages | chat/voice text | yes (free text) | purged via conversation |
| tool_calls | tool arguments and results | yes (can carry contact details) | purged via conversation |
| escalations | reason, conversation link | possible | purged via conversation |
| events | per-conversation log, `detail` text | possible (free text) | purged via conversation |
| llm_calls | provider, model, tokens, latency | no | purged via conversation |
| appointments | lead, slot link | indirect | purged via purged lead (past only; a lead with a future appointment is kept); the slot is freed |
| drafts | quote / review / follow-up drafts, JSON payload incl. `contact_email`, `customer_email` | yes | purged by `created_at` |
| intake_people | people parsed from intake, `person_key` | yes | purged by `created_at` |
| capacity_flags | capacity warnings | no | purged by `first_flagged_at` |
| brief_runs | daily brief run records | possible | purged by `created_at` |
| slots | bookable times | no | kept (config); freed when its appointment is purged |
| faq_chunks | pgvector FAQ text + 384-dim embedding | no | kept (config) |
| agent_events | append-only audit of agent actions | no by contract (ids, names, flags only) | kept; trigger blocks delete |
| tenant_api_keys | sha256 hashes of tenant keys, label, revoked_at | no | kept (credential hashes) |
| tenants | slug, name, pack reference, timezone | no | kept |

The classification of every tenant table is `PURGED` / `KEPT` in `api/app/retention.py`; the two are the single source of truth and a test fails when a new tenant table is unclassified.

Untenanted RoofDesk-own data (outbound prospecting, `db/outreach.sql`): campaigns, prospects, outreach_messages, suppressions, prospect_events, scrape_runs. Prospects hold business names, addresses, phones, emails scraped from public listings. These tables have no `tenant_id`, are not touched by tenant retention or `delete_subject`, and belong to RoofDesk, not to a customer business.

Other places data lives:

- Application logs (stdout of the api container). `mask()` replaces emails and phone numbers; see Log masking.
- n8n execution data (volume `n8ndata`). Workflow executions store request/response payloads that can include contact details. The API purge does not reach it and there is no n8n retention workflow. Whether n8n prunes executions (`EXECUTIONS_DATA_PRUNE` and related settings) is not configured in this repo: verify before relying on it.
- Mailpit (dev mail catcher, `mailpit` service): holds every email sent in dev. Not covered by retention or masking. In production `MAIL_TRANSPORT=smtp` sends through the configured SMTP account instead; copies then live in that mailbox's Sent folder.
- Ollama (host): local model; prompts are not persisted by this repo. Embeddings for FAQ come from local Ollama (`all-minilm`).
- Eval reports (`evals/reports/`): synthetic scenario text, no real customers.

## Processors

| Processor | What it receives | Location |
|---|---|---|
| local (Ollama, `LOCAL_LLM_URL`, default `llama3.1:8b`) | full prompts and conversation text | on the host; first in the chain, empty URL disables it |
| groq (`api.groq.com`) | prompts and conversation text, if `GROQ_API_KEY` is set | hosted, cross-border |
| nvidia (`integrate.api.nvidia.com`) | same, if `NVIDIA_API_KEY` is set | hosted, cross-border |
| gemini (`generativelanguage.googleapis.com`) | same, if `GEMINI_API_KEY` is set | hosted, cross-border |
| openrouter (`openrouter.ai`) | same, if `OPENROUTER_API_KEY` is set | hosted, cross-border |
| ovh (`oai.endpoints.kepler.ai.cloud.ovh.net`, key "anonymous") | same; keyless, so it is tried whenever earlier providers fail | hosted; hosting region not checked here |
| SMTP (`MAIL_TRANSPORT=smtp`, default host `smtp.gmail.com`) | outgoing email content and recipient addresses | hosted by the mailbox provider |
| n8n (self-hosted, `n8nio/n8n`) | webhook payloads and API responses it relays | local container |

The chain tries providers in order and falls through on error. The prompt is not redacted before it leaves for a hosted provider. Hosted providers only receive data when their key is set; with no keys, only local and the keyless ovh entry exist. The cross-border transfer implications of hosted providers need review.

## Retention and deletion

- `RETENTION_DAYS` (default 0 = keep everything). `POST /admin/retention/run` (admin key) or `python -m scripts.retention [--days N] [--tenant ID]` purges per tenant under RLS. Nothing runs on a schedule; there is no n8n retention workflow.
- `delete_subject`: `POST /admin/tenants/{tid}/subject/delete` (admin) and `POST /subject/delete` under the tenant router (tenant key). It erases by one identifier (email, phone digits, conversation external_id, draft contact email, intake person_key) and writes an audit event with a hash of the identifier and row counts only.
- `delete_subject` is best-effort. It finds rows linked by lead email/phone, conversation `external_id`, draft `contact_email` / `customer_email` and intake `person_key`. Drafts are matched by `contact_email`/`customer_email` only; conversations with no lead and no matching `external_id` are not matched; free text inside messages, `events.detail` and tool call arguments is not scanned; phone matching compares digits only and does not normalise country prefixes. Backups, logs, n8n execution data and Mailpit are out of reach.
- D-04 override: agent_events kept (append-only trigger, no PII by contract).
- `eval_runs` and `eval_results` have no `tenant_id`; they hold scenario ids and pass/fail only (no personal data) and are not purged.

## Log masking

`api/app/engine/mask.py` is installed as a logging filter (`PiiMaskFilter`) on root and uvicorn handlers. It masks emails and phone-like numbers in log messages, args and tracebacks and fails closed. Not covered: street addresses and names in logs, n8n execution data, Mailpit, anything stored in Postgres.

## Caveats (needs review, no legal conclusions)

- Dental pack (`bright-smile-dental`): data is synthetic demo data only. Handling real patient data may fall under special-category rules (GDPR Art. 9, Swiss nFADP); this needs review before any real use.
- Cross-border: hosted LLM providers and SMTP are outside the host's country. Transfer basis and provider terms need review.
- n8n is under the Sustainable Use License (fair-code), not an OSI open-source licence; commercial use needs review.
- The Swiss emergency number text (144) in the dental pack needs owner confirmation.
- No CI runner exists (no `.github/`); the checks run through make targets only.
- Outreach tables are untenanted RoofDesk-own data and are outside tenant retention.
