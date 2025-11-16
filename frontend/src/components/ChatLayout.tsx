import { useMemo, useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import ContextPanel from "./ContextPanel";
import SchedulerPanel from "./SchedulerPanel";
import { useDocuments } from "../hooks/useDocuments";
import { NotificationHost } from "./NotificationHost";
import { useChatSession, SessionAttachment } from "../hooks/useChatSession";
import { useChatSessionsList } from "../hooks/useChatSessionsList";
import { useAuth } from "../providers/AuthProvider";
import PanelTabs from "./PanelTabs";
import { PanelId, useChatShellState } from "../hooks/useChatShellState";
import CommandPalette from "./CommandPalette";

export default function ChatLayout() {
  const { user, signOut } = useAuth();
  if (!user) return null;

  const token = user.token;
  const {
    selectedDoc,
    setSelectedDoc,
    activeSessionId,
    selectConversation,
    activePanel,
    setActivePanel,
    handleNewChat,
  } = useChatShellState();

  const { data: chatSessions } = useChatSessionsList(token);
  const { data: documents, refetch } = useDocuments(token);

  const session = useChatSession(token, selectedDoc, activeSessionId);

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

  const [showCommandPalette, setShowCommandPalette] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "/") {
        event.preventDefault();
        setShowCommandPalette((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const commands = useMemo(
    () => [
      {
        id: "new-chat",
        label: "새 대화 시작",
        action: () => {
          handleNewChat();
          setShowCommandPalette(false);
        },
      },
      // Add more commands here
    ],
    [handleNewChat],
  );

  return (
    <div className="app-background">
      <div className="app-shell">
        <Sidebar
          conversations={chatSessions || []} // placeholder
          selectedConversation={activeSessionId}
          onSelectConversation={selectConversation}
          onNewChat={handleNewChat}
        />
        <ChatWindow
          selectedDoc={selectedDoc}
          documentOptions={documentOptions}
          onDocChange={setSelectedDoc}
          messages={session?.messages ?? []}
          loading={session?.loading ?? false}
          sendMessage={session?.sendMessage}
          attachments={session?.attachments ?? []}
          handleAttachFile={session?.handleAttachFile}
          handleRequestPromotion={session?.handleRequestPromotion}
        />
        <div 
          className="context-panel" // 바깥쪽 래퍼는 context-panel 스타일 재사용
          style={{ padding: 0, gap: 0, overflow: 'hidden' }}
        >
          {/* 탭 버튼 UI */}
          <PanelTabs
            activeId={activePanel}
            onChange={(id) => setActivePanel(id as PanelId)}
            tabs={[
              { id: "context", label: "지식 소스" },
              { id: "scheduler", label: "반복 작업" },
            ]}
          />

          {/* 탭 콘텐츠 (패널 내부에 스크롤 추가) */}
          <div style={{ flex: 1, overflowY: 'auto', background: 'rgba(10, 12, 20, 0.7)' }}>
            <div className={`fade-in-out ${activePanel === "context" ? "active" : ""}`}>
              {activePanel === "context" && (
                <ContextPanel
                  documents={documentOptions}
                  onRefresh={refetch}
                  onSelectDoc={setSelectedDoc}
                />
              )}
            </div>
            <div className={`fade-in-out ${activePanel === "scheduler" ? "active" : ""}`}>
              {activePanel === "scheduler" && (
                <SchedulerPanel />
              )}
            </div>
          </div>
        </div>
        
        <NotificationHost />
      </div>
      <CommandPalette
        isOpen={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        commands={commands}
      />
    </div>
  );
}
