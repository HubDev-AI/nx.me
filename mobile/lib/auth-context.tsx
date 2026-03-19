import { createContext, useContext, useState, useCallback } from "react";

interface AuthContextValue {
  isAuthenticated: boolean;
  setAuthenticated: (value: boolean) => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  setAuthenticated: () => {},
});

export function AuthProvider({
  children,
  initialAuth,
}: {
  children: React.ReactNode;
  initialAuth: boolean;
}) {
  const [isAuthenticated, setIsAuthenticated] = useState(initialAuth);

  const setAuthenticated = useCallback((value: boolean) => {
    setIsAuthenticated(value);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, setAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
