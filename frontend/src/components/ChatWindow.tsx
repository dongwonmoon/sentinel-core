import { useState } from "react";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { Message, SessionAttachment } from "../hooks/useChatSession";

type Props = {
  // 화면에 표시될 메시지 목록
  messages: Message[];
  // AI가 답변을 생성 중인지 여부 (로딩 상태)
  loading: boolean;
  // 사용자가 새 메시지를 보낼 때 호출될 함수
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
  isRightPanelOpen: boolean;
  onToggleRightPanel: () => void;
  onOpenUploadModal: () => void;
};

/**
 * 채팅 인터페이스의 메인 컨테이너 컴포넌트입니다.
 * 헤더, 메시지 목록, 메시지 입력창(Composer)으로 구성됩니다.
 * 상위 컴포넌트(App.tsx)로부터 상태와 로직을 props로 전달받아 UI를 렌더링하는 역할을 합니다.
 */
export default function ChatWindow({
  messages,
  loading,
  sendMessage,
  isRightPanelOpen,
  onToggleRightPanel,
  onOpenUploadModal,
}: Props) {
  // KB 등록 요청 모달을 띄울 첨부 파일 정보를 담는 상태

  return (
    <section className="chat-window">
      <header className="chat-header gemini-style-header">
        {/* 좌측 헤더 영역은 향후 브랜드나 세션명을 넣을 수 있도록 비워둔다. */}
        <div style={{ flex: 1 }}>
          {/* (헤더 좌측 공간, 필요시 앱 이름 등 표시) */}
        </div>
        {/* 컨텍스트 패널 토글은 여기서만 제어돼 상위 상태를 깔끔히 유지한다. */}
        <button 
          className="ghost gemini-icon-button"
          onClick={onToggleRightPanel}
          title={isRightPanelOpen ? "컨텍스트 패널 닫기" : "컨텍스트 패널 열기"}
        >
          {isRightPanelOpen ? "▶" : "◀"}
        </button>
      </header>

      {/* ⬇️ session-context-area 제거됨 */}

      {/* MessageList는 SSE 토큰을 그대로 넘겨받으므로 별도 상태 분리가 필요 없다. */}
      <MessageList messages={messages} sendMessage={sendMessage} />

      {/* Composer에서 onOpenUploadModal 호출 시 상위(Lay out)에서 모달이 열린다. */}
      <Composer
        disabled={loading}
        onSend={(text) => sendMessage({ query: text }) }
        // ⬇️ onAttachFile 대신 onOpenUploadModal 전달
        onOpenUploadModal={onOpenUploadModal}
      />

      {/* ⬇️ PromotionModal 렌더링 제거됨 */}
    </section>
  );
}
