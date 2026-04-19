# SUPERSEDED — Remove guest mode and FEATURE_AUTH_REQUIRED

**Date:** 2026-04-19
**Status:** SUPERSEDED after document review (six-persona review flagged P0 product, feasibility, security, coherence findings).
**Replaced by three split brainstorms:**

- `docs/brainstorms/2026-04-19-A-delete-auth-flag-and-dev-bypass-requirements.md` — delete `FEATURE_AUTH_REQUIRED` flag + `DEV_FEATURE_FOCUS` + `auth_required` capability. Safe, contained, ship now.
- `docs/brainstorms/2026-04-19-B-delete-guest-merge-plumbing-requirements.md` — remove guest→user merge primitives from payments + backend + mobile. Sequenced after payments-credits-only branch lands. Addresses actual incident source.
- `docs/brainstorms/2026-04-19-C-close-anonymous-sessions-requirements.md` — narrow public-route allowlist to auth/health/features/card-web/webhook only; add `Depends(get_current_user)` to feed, profile, comments, reactions; collapse `SessionMode` to `'user'`. Ships immediately after B.

## Why split

Review surfaced three separable decisions conflated in the umbrella:
1. Flag + dev-bypass removal (uncontroversial, no product risk).
2. Guest-merge plumbing removal (actual incident source; entangled with active payments branch).
3. Anonymous-session removal (no current consumer — card-web uses only `/v1/public/cards/*`; no scraper / SEO dependency on feed or profile; product owner confirmed closing these routes is desired). C ships immediately after B.

Original umbrella's technical errors (AUTH_ENDPOINTS.REFRESH is live, DEV_DISABLE_FEATURES has 4 other short-names, reactions endpoint inline branch missed, public-route allowlist deferred, memory edits not PR-enforceable, AC1 grep case-insensitive matches payments identifiers) are fixed inside the three split docs.
