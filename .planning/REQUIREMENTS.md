# Requirements: RoofDesk Global v1.1 Tenant-aware dashboard

**Defined:** 2026-11-05
**Core Value:** Onboarding a new business is a config pack, not a code change, and the roofing pack keeps scoring 94/96 on evals while it moves.

## v1.1 Requirements

### Sign-in and tenant shell

- [ ] **AUTH-01**: Owner can sign in on a login page by pasting their tenant API key
- [ ] **AUTH-02**: A wrong or revoked key shows a plain error and creates no session
- [ ] **AUTH-03**: Signed-in session lives in an encrypted httpOnly cookie; the key is never in page HTML, client JS or the URL
- [ ] **AUTH-04**: Any page without a session redirects to the login page
- [ ] **AUTH-05**: Owner can sign out, which clears the session
- [ ] **AUTH-06**: Header shows the business name from `GET /tenant/me`, and the nav hides screens for modules the pack does not enable
- [ ] **AUTH-07**: Every dashboard data call uses the signed-in tenant's key, so one tenant never sees another's rows

### Existing pages

- [ ] **KEEP-01**: Overview and conversations (with transcripts) render for a tenant-key session; calls, outreach and prospects (admin-only operator tools with no tenant column) stay reachable only in an operator session started by pasting the admin key, and are hidden from tenant sessions
- [ ] **KEEP-02**: The static snapshot demo mode still builds and renders without sign-in

### Drafts

- [ ] **DRAFT-01**: Owner can see quote drafts with status, customer and line items/total from `GET /drafts`
- [ ] **DRAFT-02**: A `needs_human` quote shows the reason and the missing fields
- [ ] **DRAFT-03**: Owner can approve or reject a pending quote draft; nothing is sent
- [ ] **DRAFT-04**: Owner can see review reply drafts, including blocked ones with their violation codes
- [ ] **DRAFT-05**: Owner can approve or reject a pending review reply; nothing is posted

### Capacity and brief

- [ ] **CAP-01**: Owner can see capacity flags (open by default, toggle to all) from `GET /capacity/flags`
- [ ] **BRF-01**: API exposes the latest daily brief and recent runs for the tenant (`GET`, tenant-scoped, RLS-covered)
- [ ] **BRF-02**: Owner can read the latest daily brief, with mock data labelled and unavailable sources shown

### Isolation

- [ ] **ISO-01**: A test signs in as two tenants and proves each sees only its own drafts, flags and brief

## Future Requirements

- Create/rotate tenant keys from the UI (operator does it by script today)
- Multi-user accounts per business, roles
- Edit packs from the UI
- Send approved quote or review text from the dashboard (n8n sends today)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deploy or push | Local only; user approval needed |
| Tenant creation / super-admin screens | Operator tool, `X-Admin-Key` scope stays separate |
| Pack editing | Config packs stay files in git |
| Sending or posting from the dashboard | Approve/reject only mark a decision; n8n triggers and sends |
| Changing roofing eval behaviour | Dashboard does not touch the agent; 94/96 gate must stay green |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01..07 | Phase 11 | Pending |
| KEEP-01 | Phase 11 | Pending |
| KEEP-02 | Phase 13 | Pending |
| DRAFT-01..05 | Phase 12 | Pending |
| CAP-01, BRF-01, BRF-02 | Phase 13 | Pending |
| ISO-01 | Phase 13 | Pending |

**Coverage:** 17 requirements, 17 mapped, 0 unmapped.
