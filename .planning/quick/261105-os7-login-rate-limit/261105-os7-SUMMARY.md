---
status: complete
quick_id: 261105-os7
---
# Login rate limit

Sliding-window limiter (5 failures / 15 min per client id) in `dashboard/lib/ratelimit.ts`, used by `signIn`. Blocked ids redirect to `/login?limited=1` before `checkKey`; failures counted on bad/empty/oversized key; `down` not counted; success clears. Commit 8b7b4b2.

Verified: npm run check, build, export, check_shared all exit 0. Live server-action path not exercised (could not scrape the action id for a curl POST). Stub needs no change (same exports).
