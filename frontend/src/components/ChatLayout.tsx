/**
 * @file 인증된 사용자를 위한 메인 애플리케이션 레이아웃(셸) 컴포넌트입니다.
 * @description 이 컴포넌트는 앱의 전체적인 구조(사이드바, 채팅창, 컨텍스트 패널)를 잡고,
 * 여러 커스텀 데이터 훅(hook)을 호출하여 필요한 데이터를 가져온 뒤, 이를 각각의
 * UI 컴포넌트에 주입하는 오케스트레이터(Orchestrator) 역할을 합니다.
 */

import { useState } from "react";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import { NotificationHost } from "./NotificationHost";
import { useChatSession } from "../hooks/useChatSession";
import { useChatSessionsList } from "../hooks/useChatSessionsList";
import { useAuth } from "../providers/AuthProvider";
import SessionContextPanel from "./SessionContextPanel";
import SessionUploadModal from "./SessionUploadModal";

export default function ChatLayout() {
  // --- 1. 데이터 및 상태 관리 훅 (Hooks) ---
  // 이 컴포넌트는 여러 커스텀 훅과 상태(State)를 사용하여 앱의 전반적인 상태와 데이터를 관리합니다.

  // 인증 상태 훅: `AuthProvider`로부터 현재 인증 토큰을 가져옵니다.
  // 이 토큰은 하위 데이터 훅들에서 API 요청 시 인증 헤더에 사용됩니다.
  const { token } = useAuth();

  // 현재 활성화된 채팅 세션의 ID를 관리하는 상태입니다.
  // 이 ID가 변경되면 `useChatSession` 훅이 새로운 세션 데이터를 가져옵니다.
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // 파일 업로드 모달의 열림/닫힘 상태를 관리합니다.
  const [isCodeModalOpen, setIsCodeModalOpen] = useState(false);
  // 우측 컨텍스트 패널의 열림/닫힘 상태를 관리합니다.
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true); // 우측 패널을 기본적으로 열어둡니다.

  // 방어적 코딩: 토큰이 없는 경우 (예: 로그아웃 직후 리렌더링) 아무것도 렌더링하지 않습니다.
  if (!token) return null;

  // --- 2. 데이터 페칭 커스텀 훅 ---

  // `useChatSessionsList`: 사용자의 모든 채팅 세션 목록을 가져오는 훅입니다.
  // 이 데이터는 좌측 사이드바에 표시됩니다.
  const { data: chatSessions } = useChatSessionsList(token);

  // `useChatSession`: 현재 활성화된(`activeSessionId`) 단일 채팅 세션의 상세 데이터를 관리하는 훅입니다.
  // 메시지 목록, 첨부파일 목록, 메시지 전송 함수, 로딩 상태 등을 모두 포함하고 있습니다.
  // 이 훅 내부에서 메시지 스트리밍, 첨부파일 상태 폴링 등 복잡한 로직을 모두 처리합니다.
  const session = useChatSession(token, activeSessionId);

  // --- 3. 이벤트 핸들러 ---

  /** "새 대화 시작" 버튼 클릭 시 호출됩니다. */
  const handleNewChat = () => {
    // 암호학적으로 안전한 랜덤 UUID를 생성하여 새 세션 ID로 사용합니다.
    const newSessionId = crypto.randomUUID();
    setActiveSessionId(newSessionId);
  };

  /** 사이드바에서 특정 대화를 선택했을 때 호출됩니다. */
  const handleSelectConversation = (sessionId: string | null) => {
    setActiveSessionId(sessionId);
  };

  // --- 4. UI 렌더링 ---
  return (
    <div className="app-background">
      {/* 
        전체 앱 셸(Shell) 구조입니다.
        'right-panel-visible' 또는 'right-panel-hidden' 클래스를 동적으로 적용하여
        CSS 그리드 레이아웃을 제어하고, 우측 패널의 표시 여부를 결정합니다.
      */}
      <div className={`app-shell ${isRightPanelOpen ? "right-panel-visible" : "right-panel-hidden"}`}>
        {/* 좌측 사이드바: 대화 목록 표시 및 새 대화 시작 기능 제공 */}
        <Sidebar
          conversations={chatSessions || []}
          selectedConversation={activeSessionId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
        />
        {/* 중앙 채팅창: 메시지 목록, 입력창, 파일 업로드 버튼 등 포함 */}
        <ChatWindow
          // ⬇️ document, selectedDoc, onDocChange 등 props 제거
          messages={session?.messages ?? []}
          loading={session?.loading ?? false}
          sendMessage={session.sendMessage}
          isRightPanelOpen={isRightPanelOpen}
          onToggleRightPanel={() => setIsRightPanelOpen(prev => !prev)}
          handleUploadFiles={session.handleUploadFiles}
          onOpenCodeModal={() => setIsCodeModalOpen(true)}
        />
        {/* 우측 컨텍스트 패널: 현재 세션의 첨부파일 목록 등 추가 정보 표시 */}
        <div className="right-panel-wrapper">
          <SessionContextPanel
            attachments={session?.attachments ?? []}
            onDeleteAttachment={session.handleDeleteAttachment}
          />
        </div>
        
        {/* ⬇️ right-panel-wrapper div 전체 제거 */}

        {/* 앱 전체 알림(Notification)을 호스팅하는 컴포넌트 */}
        <NotificationHost />
      </div>

      {/* 파일 업로드 모달: isUploadModalOpen 상태에 따라 표시 여부 결정 */}
      <SessionUploadModal
        isOpen={isCodeModalOpen}
        onClose={() => setIsCodeModalOpen(false)}
        sessionId={activeSessionId}
      />
    </div>
  );
}
