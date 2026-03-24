import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { getItem, setItem, deleteItem } from "./secure-storage";
import { setSessionExpiredHandler } from "./api";

const USERNAME_KEY = "nxme_username";

interface AuthContextValue {
  isAuthenticated: boolean;
  username: string | null;
  /** Non-null when the session expired and the user was force-logged-out. */
  sessionExpiredMessage: string | null;
  clearSessionExpiredMessage: () => void;
  setAuthenticated: (value: boolean) => void;
  setUsername: (value: string | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  username: null,
  sessionExpiredMessage: null,
  clearSessionExpiredMessage: () => {},
  setAuthenticated: () => {},
  setUsername: () => {},
});

export function AuthProvider({
  children,
  initialAuth,
}: {
  children: React.ReactNode;
  initialAuth: boolean;
}) {
  const [isAuthenticated, setIsAuthenticated] = useState(initialAuth);
  const [username, setUsernameState] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  // Keep a ref so the session-expired callback always sees fresh setters
  const authRef = useRef({ setIsAuthenticated, setSessionExpiredMessage });
  authRef.current = { setIsAuthenticated, setSessionExpiredMessage };

  // Register the session-expired handler once on mount
  useEffect(() => {
    setSessionExpiredHandler(() => {
      authRef.current.setIsAuthenticated(false);
      authRef.current.setSessionExpiredMessage(
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
    getItem(USERNAME_KEY).then((u) => {
      if (u) setUsernameState(u);
    }).catch((err) => { if (__DEV__) console.warn("Failed to load stored username:", err); });
  }, []);

  const setAuthenticated = useCallback((value: boolean) => {
    setIsAuthenticated(value);
    if (!value) {
      setUsernameState(null);
      deleteItem(USERNAME_KEY).catch((err) => { if (__DEV__) console.warn("Failed to clear stored username:", err); });
    }
  }, []);

  const setUsername = useCallback((value: string | null) => {
    setUsernameState(value);
    if (value) {
      setItem(USERNAME_KEY, value).catch((err) => { if (__DEV__) console.warn("Failed to persist username:", err); });
    } else {
      deleteItem(USERNAME_KEY).catch((err) => { if (__DEV__) console.warn("Failed to clear stored username:", err); });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, sessionExpiredMessage, clearSessionExpiredMessage, setAuthenticated, setUsername }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
