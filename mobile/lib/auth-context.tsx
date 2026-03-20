import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { getItem, setItem, deleteItem } from "./secure-storage";

const USERNAME_KEY = "nxme_username";

interface AuthContextValue {
  isAuthenticated: boolean;
  username: string | null;
  setAuthenticated: (value: boolean) => void;
  setUsername: (value: string | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  username: null,
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

  // Load stored username on mount
  useEffect(() => {
    getItem(USERNAME_KEY).then((u) => {
      if (u) setUsernameState(u);
    }).catch(() => {});
  }, []);

  const setAuthenticated = useCallback((value: boolean) => {
    setIsAuthenticated(value);
    if (!value) {
      setUsernameState(null);
      deleteItem(USERNAME_KEY).catch(() => {});
    }
  }, []);

  const setUsername = useCallback((value: string | null) => {
    setUsernameState(value);
    if (value) {
      setItem(USERNAME_KEY, value).catch(() => {});
    } else {
      deleteItem(USERNAME_KEY).catch(() => {});
    }
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, setAuthenticated, setUsername }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
