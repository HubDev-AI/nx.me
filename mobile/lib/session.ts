/**
 * Session mode — single source of truth for "what kind of session is this".
 *
 * Replaces the overloaded `isAuthenticated` boolean. Consumers pick the
 * predicate that matches what they actually need:
 *
 *   isUser   — has a real JWT-backed account (premium gates, posting, etc.)
 *   isGuest  — backend is in guest mode and we hold an X-Guest-Token
 *   isAnon   — no session at all (auth required + no login yet)
 *
 * Anything that needs "any session at all" (e.g., loading entitlement that
 * works for guests or users) checks `mode !== "anon"`.
 */
export type SessionMode = "user" | "guest" | "anon";

export interface SessionState {
  mode: SessionMode;
  ready: boolean;
  isUser: boolean;
  isGuest: boolean;
  isAnon: boolean;
}

export function buildSessionState(mode: SessionMode, ready: boolean): SessionState {
  return {
    mode,
    ready,
    isUser: mode === "user",
    isGuest: mode === "guest",
    isAnon: mode === "anon",
  };
}
