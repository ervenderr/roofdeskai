---
phase: 11-sign-in-and-tenant-shell
plan: 02
subsystem: dashboard
tags: [login, server-actions, nav]
requires: ["11-01"]
provides: [signIn, signOut, /login, tenant header and nav]
key-files:
  created: [dashboard/lib/session-actions.ts, dashboard/lib/session-actions.stub.ts, dashboard/app/login/page.tsx]
  modified: [dashboard/next.config.mjs, dashboard/app/layout.tsx, dashboard/app/globals.css, .env.example, README.md]
requirements: [AUTH-01, AUTH-02, AUTH-03, AUTH-05, AUTH-06, KEEP-01]
completed: 2026-11-05
---

# Phase 11 Plan 02: Login, sign-out and tenant shell Summary

Login page with signIn/signOut server actions (sealed httpOnly cookie, fixed redirect to /), session-aware header with business name badge, navFor-filtered nav and sign-out; static export swaps in a stub and is unchanged.

## Commits
- 7e4ee92 feat: login page and sign-in/sign-out server actions with export stub
- 921b2c2 feat: tenant-aware header, nav and sign-out; SESSION_SECRET in env example and README

## Verification
- `npm run build` exit 0; `.next/server/app/login.html` absent (dynamic); `.next/static` has 0 credential strings.
- `env -u API_URL EXPORT=1 npm run export` exit 0; `out/login.html` has "static demo has no sign-in", no `name="key"`; `out/index.html` has "Static demo", `/calls` link, no "Sign out".
- `npm run check`: session check ok. `python3 -m scripts.check_shared`: OK.
- Not exercised: live sign-in against the API (plan 03).

## Deviations from Plan
- README.md: only my one-line hunk was committed (via `git apply --cached`); the user's uncommitted video-line removal stays unstaged.
- Plain `npm run build` needed no SESSION_SECRET (no API_URL in this shell, pages dynamic).

## Notes
- T-11-13: admin key must be high-entropy before any deploy.
- Untracked `dashboard/tsconfig.tsbuildinfo` is build output, left uncommitted.

## Self-Check: PASSED
