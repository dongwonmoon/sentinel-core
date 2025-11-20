/**
 * @file 채팅 인터페이스의 메인 컨테이너 컴포넌트입니다.
 * @description 이 컴포넌트는 채팅창의 전체적인 구조를 잡고,
 * 헤더, 메시지 목록, 메시지 입력창(Composer)을 포함합니다.
 * 상위 컴포넌트(`ChatLayout`)로부터 상태와 로직을 props로 전달받아
 * 순수하게 UI를 렌더링하는 역할을 합니다.
 */

import MessageList from "./MessageList";
import Composer from "./Composer";
import { Message } from "../hooks/useChatSession";

type Props = {
  /** 화면에 표시될 메시지(사용자, AI, 도구 등)의 전체 목록 */
  messages: Message[];
  /** AI가 답변을 생성 중인지 여부. true일 경우 Composer가 비활성화됩니다. */
  loading: boolean;
  /**
   * 사용자가 새 메시지를 보낼 때 호출될 함수입니다.
   * `useChatSession` 훅에서 제공하는 `sendMessage` 함수가 여기에 연결됩니다.
   */
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
  /** 우측 컨텍스트 패널의 현재 열림/닫힘 상태 */
  isRightPanelOpen: boolean;
  /** 우측 컨텍스트 패널의 열림/닫힘 상태를 토글하는 함수 */
  onToggleRightPanel: () => void;
  handleUploadFiles: (files: FileList) => Promise<void>;
  onOpenCodeModal: () => void;
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
  handleUploadFiles,
  onOpenCodeModal
}: Props) {
  return (
    <section className="chat-window">
      {/* 채팅창 상단 헤더 */}
      <header className="chat-header gemini-style-header">
        {/* 좌측 헤더 영역은 향후 브랜드나 세션명을 넣을 수 있도록 비워둡니다. */}
        <div style={{ flex: 1 }}>
          {/* (헤더 좌측 공간, 필요시 앱 이름 등 표시) */}
        </div>
        {/* 우측 컨텍스트 패널을 열고 닫는 토글 버튼 */}
        <button 
          className="ghost gemini-icon-button"
          onClick={onToggleRightPanel}
          title={isRightPanelOpen ? "컨텍스트 패널 닫기" : "컨텍스트 패널 열기"}
        >
          {/* 패널 상태에 따라 아이콘 모양을 변경합니다. */}
          {isRightPanelOpen ? "▶" : "◀"}
        </button>
      </header>

      {/* 
        메시지 목록을 렌더링하는 컴포넌트입니다.
        `messages` 배열을 받아와 각 메시지 타입(user, assistant, tool)에 맞는 UI를 렌더링합니다.
      */}
      <MessageList messages={messages} sendMessage={sendMessage} />

      {/* 
        사용자 입력을 받는 메시지 작성기(Composer) 컴포넌트입니다.
        AI가 응답 중일 때(`loading`이 true)는 입력창을 비활성화합니다.
        `onSend` 콜백을 통해 사용자가 입력한 텍스트를 `sendMessage` 함수로 전달합니다.
        `onOpenUploadModal` 콜백을 통해 파일 첨부 버튼 클릭 시 업로드 모달을 열도록 합니다.
      */}
      <Composer
        disabled={loading}
        onSend={(text) => sendMessage({ query: text }) }
        handleUploadFiles={handleUploadFiles}
        onOpenCodeModal={onOpenCodeModal}
      />
    </section>>
  );
}
