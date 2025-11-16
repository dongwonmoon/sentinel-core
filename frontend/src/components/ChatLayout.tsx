/**
 * @file 인증된 사용자를 위한 메인 애플리케이션 레이아웃(셸) 컴포넌트입니다.
 * @description 이 컴포넌트는 앱의 전체적인 구조를 잡고, 여러 데이터 훅(hook)을 호출하여
 * 필요한 데이터를 가져온 뒤, 이를 각각의 UI 컴포넌트(사이드바, 채팅창, 컨텍스트 패널 등)에
 * 주입하는 오케스트레이터 역할을 합니다.
 */

import { useMemo, useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import ContextPanel from "./ContextPanel";
import SchedulerPanel from "./SchedulerPanel";
import { useDocuments } from "../hooks/useDocuments";
import { NotificationHost } from "./NotificationHost";
import { useChatSession } from "../hooks/useChatSession";
import { useChatSessionsList } from "../hooks/useChatSessionsList";
import { useAuth } from "../providers/AuthProvider";
import PanelTabs from "./PanelTabs";
import { PanelId, useChatShellState } from "../hooks/useChatShellState";
import CommandPalette from "./CommandPalette";

export default function ChatLayout() {
  // --- 1. 데이터 및 상태 관리 훅 (Hooks) ---
  // 이 컴포넌트는 여러 커스텀 훅을 사용하여 앱의 상태와 데이터를 관리합니다.

  // 인증 상태 훅: 현재 로그인된 사용자 정보와 로그아웃 함수를 가져옵니다.
  const { user, token } = useAuth();
  // 전역 UI 상태 훅: 활성 세션 ID, 활성 패널 등 앱의 전반적인 UI 상태를 관리합니다.
  const {
    activeSessionId,
    selectConversation,
    activePanel,
    setActivePanel,
    handleNewChat,
    selectedDoc,
    setSelectedDoc,
  } = useChatShellState();

  if (!token) return null; // 토큰이 없으면 렌더링하지 않음 (방어적 코딩)

  // 사이드바에 표시될 전체 채팅 세션 목록을 가져옵니다.
  const { data: chatSessions } = useChatSessionsList(token);
  // 컨텍스트 패널에 표시될 전체 문서 목록을 가져옵니다.
  const { data: documents, refetch: refetchDocs } = useDocuments(token);
  // 현재 활성화된 단일 채팅 세션의 상세 데이터(메시지, 첨부파일 등)와 로직을 관리합니다.
  const session = useChatSession(token, activeSessionId);

  // --- 2. 메모이제이션 및 파생 상태 (Memoization & Derived State) ---

  // `documents` 데이터가 변경될 때만 문서 목록 옵션을 다시 계산합니다.
  // `useMemo`를 사용하여 불필요한 리렌더링을 방지하는 최적화 기법입니다.
  const documentOptions = useMemo(
    () =>
      documents
        ? Object.entries(documents).map(([id, name]) => ({
            id,
            name,
          }))
        : [],
    [documents]
  );

  // --- 3. 커맨드 팔레트 상태 및 이벤트 핸들러 ---
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);

  // '/' 키를 누르면 커맨드 팔레트를 열기 위한 전역 이벤트 리스너를 등록합니다.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "/") {
        event.preventDefault(); // 기본 동작(예: 빠른 찾기) 방지
        setShowCommandPalette((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    // 컴포넌트가 언마운트될 때 이벤트 리스너를 제거하여 메모리 누수를 방지합니다. (Cleanup)
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // 커맨드 팔레트에 표시될 명령어 목록입니다.
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
      // 향후 여기에 더 많은 명령어를 추가할 수 있습니다.
    ],
    [handleNewChat]
  );

  // --- 4. UI 렌더링 ---
  return (
    <div className="app-background">
      <div className={`app-shell ${isRightPanelOpen ? "right-panel-visible" : "right-panel-hidden"}`}>
        {/* 좌측 사이드바: 대화 목록 표시 및 새 대화 시작 */}
        <Sidebar
          conversations={chatSessions || []}
          selectedConversation={activeSessionId}
          onSelectConversation={selectConversation}
          onNewChat={handleNewChat}
        />
        {/* 중앙 채팅창: 메시지 표시, 새 메시지 작성, 파일 첨부 등 */}
        <ChatWindow
          documentOptions={documentOptions}
          selectedDoc={selectedDoc}
          onDocChange={setSelectedDoc}
          messages={session?.messages ?? []}
          loading={session?.loading ?? false}
          sendMessage={session?.sendMessage}
          attachments={session?.attachments ?? []}
          handleAttachFile={session?.handleAttachFile}
          handleRequestPromotion={session?.handleRequestPromotion}
          isRightPanelOpen={isRightPanelOpen}
          onToggleRightPanel={() => setIsRightPanelOpen(prev => !prev)}
        />
        <div className="right-panel-wrapper">
          <div
            className="context-panel" 
            style={{ padding: 0, gap: 0, overflow: "hidden", height: '100%' }}
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

            {/* 탭 콘텐츠 */}
            <div
              style={{ flex: 1, overflowY: "auto", background: "rgba(10, 12, 20, 0.7)" }}
            >
              <div
                className={`fade-in-out ${
                  activePanel === "context" ? "active" : ""
                }`}
              >
                {activePanel === "context" && (
                  <ContextPanel
                    documents={documentOptions}
                    onRefresh={refetchDocs}
                    onSelectDoc={setSelectedDoc}
                  />
                )}
              </div>
              <div
                className={`fade-in-out ${
                  activePanel === "scheduler" ? "active" : ""
                }`}
              >
                {activePanel === "scheduler" && <SchedulerPanel />}
              </div>
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