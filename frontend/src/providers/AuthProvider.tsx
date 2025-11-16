import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  ReactNode,
} from "react";
import { User } from "../schemas";

export type AuthResult = { token: string; user: User };

type AuthContextValue = {
  user: User | null;
  token: string | null;
  signIn: (next: AuthResult) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem("sentinel_token")
  );
  const [user, setUser] = useState<User | null>(() => {
    const userJson = localStorage.getItem("sentinel_user");
    if (!userJson) return null;
    try {
      return JSON.parse(userJson) as User;
    } catch {
      return null;
    }
  });

  const signIn = useCallback((next: AuthResult) => {
    localStorage.setItem("sentinel_token", next.token);
    localStorage.setItem("sentinel_user", JSON.stringify(next.user));
    setToken(next.token);
    setUser(next.user);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem("sentinel_token");
    localStorage.removeItem("sentinel_user");
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      signIn,
      signOut,
    }),
    [user, token, signIn, signOut],
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
