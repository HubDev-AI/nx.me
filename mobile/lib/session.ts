/**
 * Session mode — single source of truth for "what kind of session is this".
 *
 * Consumers pick the predicate that matches what they actually need:
 *
 *   isUser   — has a real JWT-backed account (premium gates, posting, etc.)
 *   isAnon   — no session (user is logged out or has never logged in)
 */
export type SessionMode = "user" | "anon";

export interface SessionState {
  mode: SessionMode;
  ready: boolean;
  isUser: boolean;
  isAnon: boolean;
}

export function buildSessionState(mode: SessionMode, ready: boolean): SessionState {
  return {
    mode,
    ready,
    isUser: mode === "user",
    isAnon: mode === "anon",
  };
}
