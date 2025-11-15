import { useMemo } from "react";
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import AuthView from "./components/AuthView";
import ChatLayout from "./components/ChatLayout";
import { AuthProvider, useAuth } from "./providers/AuthProvider";

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
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}

function AuthenticatedApp() {
  const { user, signIn } = useAuth();
  const client = useMemo(() => createClient(), []);

  if (!user) {
    return <AuthView onSuccess={signIn} />;
  }

  return (
    <QueryClientProvider client={client}>
      <ChatLayout />
    </QueryClientProvider>
  );
}
