import { useMemo, useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  QueryCache,
} from "@tanstack/react-query";
import AuthView, { AuthResult } from "./components/AuthView";
import ChatLayout from "./components/ChatLayout";

function createClient() {
  return new QueryClient({
    queryCache: new QueryCache(),
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export default function App() {
  const [auth, setAuth] = useState<AuthResult | null>(() => {
    const token = localStorage.getItem("sentinel_token");
    const username = localStorage.getItem("sentinel_username");
    if (!token || !username) return null;
    return { token, username };
  });

  const client = useMemo(() => createClient(), []);

  if (!auth) {
    return <AuthView onSuccess={(next) => handleAuth(next, setAuth)} />;
  }

  return (
    <QueryClientProvider client={client}>
      <ChatLayout auth={auth} onSignOut={() => handleSignOut(setAuth)} />
    </QueryClientProvider>
  );
}

function handleAuth(next: AuthResult, setter: (value: AuthResult) => void) {
  localStorage.setItem("sentinel_token", next.token);
  localStorage.setItem("sentinel_username", next.username);
  setter(next);
}

function handleSignOut(setter: (value: null) => void) {
  localStorage.removeItem("sentinel_token");
  localStorage.removeItem("sentinel_username");
  setter(null);
}
