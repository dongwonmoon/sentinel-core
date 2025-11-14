import { useMemo, useState } from "react";
import { AuthResult } from "./AuthView";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import ContextPanel from "./ContextPanel";
import { useDocuments } from "../hooks/useDocuments";
import { NotificationHost } from "./NotificationHost";
import { useChatSession } from "../hooks/useChatSession";
import { useChatSessionsList } from "../hooks/useChatSessionsList";

type Props = {
  auth: AuthResult;
  onSignOut: () => void;
};

export default function ChatLayout({ auth, onSignOut }: Props) {
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { data: chatSessions } = useChatSessionsList(auth.token);
  const { data: documents, refetch } = useDocuments(auth.token);
  const session = useChatSession(auth.token, selectedDoc, activeSessionId);

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

  const handleNewChat = () => {
    // crypto.randomUUID()는 브라우저 기본 기능으로 고유 ID 생성
    setActiveSessionId(crypto.randomUUID());
  };

  return (
    <div className="app-background">
      <div className="app-shell">
        <Sidebar
          username={auth.username}
          onSignOut={onSignOut}
          conversations={chatSessions || []} // placeholder
          selectedConversation={activeSessionId}
          onSelectConversation={setActiveSessionId}
          onNewChat={handleNewChat}
        />
        <ChatWindow
          auth={auth}
          selectedDoc={selectedDoc}
          documentOptions={documentOptions}
          onDocChange={setSelectedDoc}
          messages={session.messages}
          loading={session.loading}
          sendMessage={session.sendMessage}
        />
        <ContextPanel
          auth={auth}
          documents={documentOptions}
          onRefresh={refetch}
          onSelectDoc={setSelectedDoc}
        />
        <NotificationHost />
      </div>
    </div>
  );
}
