import { useMemo, useState } from "react";
import { AuthResult } from "./AuthView";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import ContextPanel from "./ContextPanel";
import { useDocuments } from "../hooks/useDocuments";
import { NotificationHost } from "./NotificationHost";

type Props = {
  auth: AuthResult;
  onSignOut: () => void;
};

export default function ChatLayout({ auth, onSignOut }: Props) {
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const { data: documents, refetch } = useDocuments(auth.token);

  const documentOptions = useMemo(
    () =>
      documents
        ? Object.entries(documents).map(([id, name]) => ({
            id,
            name,
          }))
        : [],
    [documents],
  );

  return (
    <div className="app-shell">
      <Sidebar
        username={auth.username}
        onSignOut={onSignOut}
        conversations={[]} // placeholder
        selectedConversation={selectedConversation}
        onSelectConversation={setSelectedConversation}
      />
      <ChatWindow
        auth={auth}
        selectedDoc={selectedDoc}
        documentOptions={documentOptions}
        onDocChange={setSelectedDoc}
      />
      <ContextPanel
        auth={auth}
        documents={documentOptions}
        onRefresh={refetch}
        onSelectDoc={setSelectedDoc}
      />
      <NotificationHost />
    </div>
  );
}
