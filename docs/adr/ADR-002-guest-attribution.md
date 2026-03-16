# ADR-002: Guest Attribution Strategy

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Engineering, Product
**Tags:** guest, attribution, session, analytics, FR-20

---

## Context

NXME allows unauthenticated browsing of social content (posts, reactions). Guests who later create accounts should have their pre-registration activity attributed correctly for analytics and potentially for product features (e.g., retaining liked posts or surfacing content they engaged with).

The challenge: guests have no persistent identity on the server. Two attribution strategies were considered:
1. **Device fingerprinting** — derive an ID from device hardware/OS
2. **CSPRNG token** — issue a random durable token at first app open

A separate but related question (OQ-1) concerns whether guest reactions should be retroactively attributed to an account on registration. This is resolved in ADR-003.

---

## Decision

**Issue a durable 32-byte CSPRNG guest_session_token at first app open.**

On first app launch (before any account creation):
1. Generate `guest_session_token = secrets.token_hex(32)` (256-bit random token)
2. Store in **Expo SecureStore** on the device — survives app restarts, cleared on uninstall/factory reset
3. Send with all API requests as `X-Guest-Session: {token}` header
4. Server stores `guest_session_token` in a Redis hash with 365-day TTL; refreshed on each API call

On account creation:
- The `guest_session_token` is sent with the registration request
- Server links `users.guest_session_token = token` in the users table (nullable column)
- Attribution query: `SELECT * FROM analytics_events WHERE guest_session_token = ?` to backfill analytics

---

## Token Properties

| Property | Value |
|----------|-------|
| Generation | `secrets.token_hex(32)` — 256-bit CSPRNG |
| Storage (client) | Expo SecureStore (hardware-backed on supported devices) |
| Storage (server) | Redis hash `guest:{token}` with 365-day TTL |
| Transport | `X-Guest-Session` request header |
| Server-side TTL | 365 days, refreshed on each request |
| Persistence across reinstall | No (SecureStore cleared on uninstall) |
| Uniqueness | Cryptographically guaranteed |

---

## Analytics Attribution on Account Creation

When a guest creates an account:
1. Client sends `guest_session_token` in the registration request body
2. `users.guest_session_token` is set (nullable UUID column in users table)
3. Analytics pipeline can join `analytics_events.guest_session_token` with `users.guest_session_token` to attribute pre-registration behavior to the new account
4. The Redis guest hash is deleted after successful attribution to avoid stale references

Pre-registration content interactions (what posts the guest viewed, how long they stayed) are attributed. Reactions are handled separately per ADR-003.

---

## Why Not Device Fingerprinting

| Concern | Detail |
|---------|--------|
| Privacy regulation | App Tracking Transparency (iOS 14.5+) requires explicit opt-in for cross-app tracking; fingerprinting may trigger this |
| Accuracy | Device IDs change on OS update, factory reset, or when user clears advertising ID |
| App store policy | Apple/Google restrict fingerprinting approaches; CSPRNG tokens are policy-compliant |
| Implementation | SecureStore token is simpler, more reliable, and requires no special permissions |

---

## Consequences

**Benefits:**
- Simple, reliable, policy-compliant attribution mechanism
- No device permission required
- Cryptographically collision-resistant
- Works the same on iOS and Android

**Tradeoffs:**
- Token is lost on app uninstall — guest history cannot be recovered after reinstall
- If user uses multiple devices before registering, sessions are separate (no cross-device merging)
- Server must maintain Redis records for up to 365 days per active guest

**Accepted tradeoffs:** Multi-device merging before registration is an edge case not worth the complexity. Token loss on reinstall is expected user behavior.
