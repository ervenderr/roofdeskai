# Deploying (free tiers)

Only the dashboard is hosted by default. It is a static export of a snapshot of the demo data, so it needs no
backend, no secrets and no database.

## 1. Dashboard on Cloudflare Pages (static demo)

```bash
docker compose exec api python -m scripts.export_snapshot > dashboard/data/snapshot.json
cd dashboard && npm ci && npm run export     # writes dashboard/out
```

Pages settings: root directory `dashboard`, build command `npm run export`, output directory `out`.
No environment variables. The snapshot is synthetic (made-up names, numbers, addresses).

## 2. Live stack (optional)

| Piece | Service | Notes |
|---|---|---|
| Dashboard (live) | Cloudflare Pages / Next on Node | Set `API_URL` and `ADMIN_API_KEY` as server-side variables. Never expose the admin key to the browser. |
| Database | Neon | Postgres with pgvector. Run `db/init.sql` once. Set `DATABASE_URL` (`postgresql+psycopg://...`). |
| API | Any container host with a free tier (Render, Koyeb, Fly) | Free tiers sleep when idle, so the first request is slow. `api/Dockerfile` is the image. Remove `--reload` for production. |
| LLM | Groq / NVIDIA NIM / OpenRouter keys | Set `GROQ_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`. The local Ollama entry is skipped when unreachable; its failure is handled like any other provider error. Embeddings (`lookup_faq`) currently need an Ollama-compatible `/v1/embeddings` endpoint (`LOCAL_LLM_URL`); a hosted host has none, so use a small embeddings API or run Ollama alongside. |
| Auth for admin pages | Clerk | Not wired yet. Until it is, the admin endpoints are protected by `X-Admin-Key` only. |
| Email | Resend | Not wired yet. n8n and the outreach engine send through Mailpit in dev. Swap the HTTP Request URL in each n8n workflow, and the one function in `api/app/mailer.py`, for Resend (`https://api.resend.com/emails`, bearer token). For cold outreach use a separate sending domain with SPF, DKIM and DMARC, warm it up, keep the daily cap low, and set `SENDER_ADDRESS` (the API refuses to send without it). |
| n8n | Local only | Needs an always-on host; free tiers sleep. Export JSON in `n8n/workflows/` plus the demo video show it running. |

## Before the API is public
- `/chat` already needs the per-conversation token and is rate limited (20 messages/min per IP, in-process).
- Set a strong `ADMIN_API_KEY`; the dev default is `dev-admin-key`.
- Behind a proxy, `request.client.host` is the proxy's address, so the rate limit would be shared. Put the limit at the edge or read the forwarded header from a trusted proxy.
- Do not publish `/webhooks/inbound`; only n8n should reach it.
