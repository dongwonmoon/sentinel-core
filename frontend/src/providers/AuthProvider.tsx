import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  ReactNode,
} from "react";

export type AuthResult = { token: string; username: string };

type AuthContextValue = {
  user: AuthResult | null;
  signIn: (next: AuthResult) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthResult | null>(() => {
    const token = localStorage.getItem("sentinel_token");
    const username = localStorage.getItem("sentinel_username");
    if (!token || !username) return null;
    return { token, username };
  });

  const signIn = useCallback((next: AuthResult) => {
    localStorage.setItem("sentinel_token", next.token);
    localStorage.setItem("sentinel_username", next.username);
    setUser(next);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem("sentinel_token");
    localStorage.removeItem("sentinel_username");
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      signIn,
      signOut,
    }),
    [user, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth는 AuthProvider 안에서만 사용 가능합니다.");
  }
  return ctx;
}
