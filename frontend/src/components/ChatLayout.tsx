import { useMemo, useState } from "react";
import { AuthResult } from "./AuthView";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import ContextPanel from "./ContextPanel";
import SchedulerPanel from "./SchedulerPanel";
import { useDocuments } from "../hooks/useDocuments";
import { NotificationHost } from "./NotificationHost";
import { useChatSession } from "../hooks/useChatSession";
import { useChatSessionsList } from "../hooks/useChatSessionsList";

type Props = {
  auth: AuthResult;
  onSignOut: () => void;
};

type ActivePanel = "context" | "scheduler";

export default function ChatLayout({ auth, onSignOut }: Props) {
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanel>("context");

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
          token={auth.token}
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
          messages={session?.messages ?? []}
          loading={session?.loading ?? false}
          sendMessage={session?.sendMessage}
        />
        <div 
          className="context-panel" // 바깥쪽 래퍼는 context-panel 스타일 재사용
          style={{ padding: 0, gap: 0, overflow: 'hidden' }}
        >
          {/* 탭 버튼 UI */}
          <div style={{ display: "flex", borderBottom: '1px solid rgba(148, 163, 184, 0.15)' }}>
            <button
              className={activePanel === "context" ? "list-item active" : "list-item"}
              onClick={() => setActivePanel("context")}
              style={{ flex: 1, borderRadius: 0 }}
            >
              지식 소스
            </button>
            <button
              className={activePanel === "scheduler" ? "list-item active" : "list-item"}
              onClick={() => setActivePanel("scheduler")}
              style={{ flex: 1, borderRadius: 0 }}
            >
              반복 작업
            </button>
          </div>

          {/* 탭 콘텐츠 (패널 내부에 스크롤 추가) */}
          <div style={{ flex: 1, overflowY: 'auto', background: 'rgba(10, 12, 20, 0.7)' }}>
            {activePanel === "context" ? (
              <ContextPanel
                auth={auth}
                documents={documentOptions}
                onRefresh={refetch}
                onSelectDoc={setSelectedDoc}
              />
            ) : (
              <SchedulerPanel auth={auth} />
            )}
          </div>
        </div>
        
        <NotificationHost />
      </div>
    </div>
  );
}
