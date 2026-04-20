import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { getItem, setItem, deleteItem } from "./secure-storage";
import { setSessionExpiredHandler } from "./api";
import { buildSessionState, type SessionMode, type SessionState } from "./session";
import { SECURE_STORE_KEYS } from "../constants/config";

interface AuthContextValue {
  /** Resolved session — single source of truth, no more booleans. */
  session: SessionState;
  username: string | null;
  /** Non-null when the session expired and the user was force-logged-out. */
  sessionExpiredMessage: string | null;
  clearSessionExpiredMessage: () => void;
  /** Set the session mode explicitly. Real login → "user", logout → "anon". */
  setSessionMode: (mode: SessionMode) => void;
  /** Mark the session as bootstrapped (features loaded + token resolution attempted). */
  markSessionReady: () => void;
  setUsername: (value: string | null) => void;
}

const DEFAULT_SESSION = buildSessionState("anon", false);

const AuthContext = createContext<AuthContextValue>({
  session: DEFAULT_SESSION,
  username: null,
  sessionExpiredMessage: null,
  clearSessionExpiredMessage: () => {},
  setSessionMode: () => {},
  markSessionReady: () => {},
  setUsername: () => {},
});

export function AuthProvider({
  children,
  initialMode,
}: {
  children: React.ReactNode;
  initialMode: SessionMode;
}) {
  const [session, setSession] = useState<SessionState>(() =>
    buildSessionState(initialMode, false),
  );
  const [username, setUsernameState] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  const sessionRef = useRef({ setSession, setSessionExpiredMessage });
  sessionRef.current = { setSession, setSessionExpiredMessage };

  // Register the session-expired handler once on mount
  useEffect(() => {
    setSessionExpiredHandler(() => {
      sessionRef.current.setSession((prev) => buildSessionState("anon", prev.ready));
      sessionRef.current.setSessionExpiredMessage(
        "Your session has expired. Please sign in again.",
      );
    });
    return () => setSessionExpiredHandler(() => {});
  }, []);

  const clearSessionExpiredMessage = useCallback(() => {
    setSessionExpiredMessage(null);
  }, []);

  // Load stored username on mount
  useEffect(() => {
    getItem(SECURE_STORE_KEYS.USERNAME).then((u) => {
      if (u) setUsernameState(u);
    }).catch((err) => { if (__DEV__) console.warn("Failed to load stored username:", err); });
  }, []);

  const setSessionMode = useCallback((mode: SessionMode) => {
    setSession((prev) => buildSessionState(mode, prev.ready));
    if (mode === "anon") {
      setUsernameState(null);
      deleteItem(SECURE_STORE_KEYS.USERNAME).catch((err) => { if (__DEV__) console.warn("Failed to clear stored username:", err); });
    }
  }, []);

  const markSessionReady = useCallback(() => {
    setSession((prev) => (prev.ready ? prev : buildSessionState(prev.mode, true)));
  }, []);

  const setUsername = useCallback((value: string | null) => {
    setUsernameState(value);
    if (value) {
      setItem(SECURE_STORE_KEYS.USERNAME, value).catch((err) => { if (__DEV__) console.warn("Failed to persist username:", err); });
    } else {
      deleteItem(SECURE_STORE_KEYS.USERNAME).catch((err) => { if (__DEV__) console.warn("Failed to clear stored username:", err); });
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        session,
        username,
        sessionExpiredMessage,
        clearSessionExpiredMessage,
        setSessionMode,
        markSessionReady,
        setUsername,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/** Convenience hook — returns just the SessionState. */
export function useSession(): SessionState {
  return useContext(AuthContext).session;
}
