# ADR-003: Guest Reaction Attribution (OQ-1 Resolution)

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Engineering, Product
**Tags:** guest, reactions, attribution, OQ-1, FR-20, Story 5-2 prerequisite

---

## Context

OQ-1 (Open Question 1 from architecture phase): Should guest reactions be retroactively attributed to a user account when the guest registers?

**Example scenario:**
1. Guest browses NXME feed without an account
2. Guest taps a 🔥 reaction on a post
3. Guest creates an account
4. Question: Does the 🔥 reaction now appear under their account? Does the post author see it as coming from a registered user?

This decision must be documented before Story 5-2 (Reactions API) enters implementation, as the reactions schema and API design depend on it.

---

## Decision

**Guest reactions are session-scoped (ephemeral) — they are NOT retroactively attributed to an account on registration.**

When a guest reacts to a post:
- The reaction is stored temporarily with `guest_session_token` as identifier (in-memory or short-TTL Redis, NOT in the `reactions` table)
- Reactions are visible to the guest during their current session (client-side state)
- On app restart or session expiry, guest reactions are gone
- On account creation, NO backfill of guest reactions occurs

After registration, the user reacts as a registered user — all future reactions are stored in the `reactions` table with `user_id`.

---

## Rationale

### 1. Reaction integrity and spam prevention

Retroactive attribution creates a window for abuse: a bad actor can create N guest sessions, react to their own post N times, then register to permanently inflate their reaction count. Session-scoped reactions close this window because unauthenticated reactions never persist.

### 2. Social graph consistency

The reactions table uses `user_id NOT NULL`. Allowing guest reactions would require either:
- A nullable `user_id` with fallback to `guest_session_token` — complicates all reaction queries and counts
- Post-registration migration — introduces a two-phase write that can fail or be double-applied

Both options add complexity for a low-value feature (most users register before extensively reacting).

### 3. Product signal value

Analytics on guest reactions (which posts attracted registrations from guests who reacted) IS preserved via ADR-002's analytics attribution: the `guest_session_token` in analytics events links pre-registration engagement to accounts. Product can observe "user X reacted to post Y as a guest before registering" via analytics without persisting reactions as social graph records.

### 4. User expectation

Users creating accounts expect to start fresh. Surfacing old "ghost" reactions from before they had an account is likely surprising and potentially confusing ("I don't remember reacting to that").

---

## Schema Implications for Story 5-2

The `reactions` table requires `user_id NOT NULL`:

```sql
CREATE TABLE reactions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id      UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    emoji        TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (post_id, user_id, emoji)
);
```

Guest reaction display (showing guests their own tap without persistence) is handled client-side using local state. The API endpoint `POST /posts/{id}/reactions` requires authentication — unauthenticated requests return HTTP 401 with a registration prompt.

---

## API Contract for Story 5-2

```
POST /posts/{post_id}/reactions          → requires auth (HTTP 401 if guest)
DELETE /posts/{post_id}/reactions/{id}   → requires auth
GET /posts/{post_id}/reactions           → public (aggregated counts only, no user identities)
```

Guest reaction persistence endpoint: **does not exist** — not implemented.

---

## Consequences

**Benefits:**
- Clean reactions table schema (user_id NOT NULL, no nullable guest column)
- No retroactive attribution race conditions
- Reaction counts are trustworthy (no ghost inflation from multi-session guests)

**Tradeoffs:**
- Guest who reacts to a post and then registers loses that reaction — minor UX friction
- Product cannot display "you reacted to this before you joined" — acceptable

**Accepted tradeoff:** The UX friction is minimal. The integrity and complexity benefits outweigh the "save my guest reactions" feature.

---

## Prerequisite Status

This ADR must be accepted before Story 5-2 (Reactions API) enters implementation, per plan AC-D3. Status: **Accepted** ✅
