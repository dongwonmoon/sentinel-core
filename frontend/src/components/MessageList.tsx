/**
 * @file 채팅 메시지 목록을 렌더링하는 UI 컴포넌트입니다.
 * @description 이 컴포넌트는 메시지 배열을 받아 각 메시지를 적절한 UI로 렌더링합니다.
 * 주요 기능:
 * - 사용자, AI, 도구 호출 등 다양한 역할(role)에 따른 메시지 스타일링
 * - AI 응답 내의 마크다운(Markdown) 렌더링
 * - 마크다운 내 코드 블록에 대한 구문 강조(Syntax Highlighting) 및 복사 기능
 * - 새 메시지 수신 시 자동 스크롤 및 '최신 메시지 보기' 버튼 제어
 * - 너무 많은 메시지가 DOM에 렌더링되는 것을 방지하기 위한 메시지 수 제한
 * - RAG 답변의 출처(Source) 표시 및 상세 정보 모달
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "../hooks/useChatSession";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import Modal from "./Modal";
import EmptyChatWindow from "./EmptyChatWindow";
import ToolCallWidget from "./ToolCallWidget";

type Props = {
  /** 화면에 표시될 메시지(사용자, AI, 도구 등)의 전체 목록 */
  messages: Message[];
  /**
   * 메시지 재생성 등 내부에서 메시지를 다시 보내야 할 때 사용할 함수.
   * `useChatSession` 훅에서 제공하는 `sendMessage` 함수가 여기에 연결됩니다.
   */
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
};

/** 화면에 한 번에 표시할 최대 메시지 수. 성능 최적화를 위해 사용됩니다. */
const MAX_VISIBLE_MESSAGES = 150;

// =================================================================
// 마크다운 렌더링을 위한 코드 블록 구문 강조(Syntax Highlighting) 컴포넌트
// =================================================================

/**
 * `ReactMarkdown` 라이브러리를 통해 코드 블록(```)을 렌더링할 때 사용되는 커스텀 컴포넌트입니다.
 * `react-syntax-highlighter`를 사용하여 구문을 강조하고, 우측 상단에 '복사' 버튼을 추가합니다.
 * `React.memo`와 유사하게, props가 변경되지 않으면 리렌더링을 방지하여 성능을 최적화합니다.
 */
const MemoizedSyntaxHighlighter = ({ children, className, ...props }: any) => {
  // className에서 언어 정보를 추출합니다 (예: "language-python" -> "python").
  const match = /language-(\w+)/.exec(className || "");
  const codeContent = String(children).replace(/\n$/, "");

  /** '복사' 버튼 클릭 시 코드 내용을 클립보드에 복사하는 핸들러입니다. */
  const handleCopyClick = async () => {
    try {
      await navigator.clipboard.writeText(codeContent);
      // TODO: "복사됨!"과 같은 사용자 피드백을 토스트 메시지 등으로 제공하면 더 좋습니다.
      console.log("Code copied to clipboard!");
    } catch (err) {
      console.error("Failed to copy code:", err);
    }
  };

  // 언어 정보가 없으면 일반 `<code>` 태그로 렌더링합니다.
  if (!match) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  }

  // 언어 정보가 있으면 구문 강조 컴포넌트를 렌더링합니다.
  return (
    <div style={{ position: "relative" }}>
      <SyntaxHighlighter
        style={vscDarkPlus} // VS Code 다크 테마와 유사한 스타일 적용
        language={match[1]}
        PreTag="div"
        {...props}
      >
        {codeContent}
      </SyntaxHighlighter>

      {/* 코드 복사 버튼 */}
      <button
        onClick={handleCopyClick}
        style={{
          position: "absolute",
          top: "0.5em",
          right: "0.5em",
          background: "rgba(255, 255, 255, 0.2)",
          border: "none",
          borderRadius: "3px",
          color: "white",
          padding: "0.3em 0.6em",
          cursor: "pointer",
          fontSize: "0.8em",
        }}
      >
        Copy
      </button>
    </div>
  );
};

/** `ReactMarkdown`에 전달될 컴포넌트 매핑 객체입니다. */
const markdownComponents = {
  // `code` 태그를 렌더링할 때 `MemoizedSyntaxHighlighter`를 사용하도록 재정의합니다.
  code({ inline, className, children, ...props }: any) {
    return inline ? (
      // 인라인 코드(`code`)는 기본 렌더링을 사용합니다.
      <code className={className} {...props}>
        {children}
      </code>
    ) : (
      // 블록 코드(```code```)는 커스텀 컴포넌트를 사용합니다.
      <MemoizedSyntaxHighlighter className={className} {...props}>
        {children}
      </MemoizedSyntaxHighlighter>
    );
  },
};

// ======================================================
// MessageList Component
// ======================================================

/**
 * 채팅 메시지, 도구 이벤트, 소스 모달을 모두 렌더링하는 메인 컨테이너입니다.
 * SSE 스트림에서 받은 `Message` 배열을 그대로 표시하고, 사용자의 스크롤 위치에 따라
 * 자동 스크롤 또는 '최신 메시지 보기' 버튼 표시를 제어합니다.
 */
export default function MessageList({ messages, sendMessage }: Props) {
  // 메시지 목록을 담는 컨테이너 div에 대한 참조(reference)
  const containerRef = useRef<HTMLDivElement>(null);
  // 이전 메시지 개수를 저장하여 새 메시지가 추가되었는지 판별하는 데 사용
  const previousLength = useRef(0);

  // 사용자가 스크롤을 맨 아래에 위치시켰는지 여부를 추적하는 상태
  const [isAtBottom, setIsAtBottom] = useState(true);
  // '최신 메시지 보기' 버튼의 표시 여부를 제어하는 상태
  const [showJumpButton, setShowJumpButton] = useState(false);

  // RAG 출처(Source) 상세 정보를 보여주는 모달의 상태
  const [showSourceModal, setShowSourceModal] = useState(false);
  // 사용자가 클릭한 출처의 내용을 저장하는 상태
  const [selectedSource, setSelectedSource] = useState<string | null>(null);

  /**
   * 메시지 목록을 부드럽게 맨 아래로 스크롤합니다.
   */
  const scrollToBottom = () => {
    const node = containerRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  };

  // --- 자동 스크롤 및 '최신 메시지 보기' 버튼 로직 ---
  // 이 useEffect는 스크롤 위치를 감지하고 isAtBottom 상태를 업데이트합니다.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const handleScroll = () => {
      // 스크롤 위치가 맨 아래에서 약간의 오차(10px) 내에 있는지 확인합니다.
      const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 10;
      setIsAtBottom(atBottom);
    };

    node.addEventListener("scroll", handleScroll);
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  // 이 useEffect는 새 메시지가 도착했을 때 스크롤 동작을 결정합니다.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
    
    // 1. 방금 추가된 메시지가 'user' 메시지인지 확인합니다.
    const isNewUserMessage = lastMessage?.role === 'user' && messages.length > previousLength.current;

    // 2. 새 메시지가 'user' 타입이면, 사용자가 어디를 보고 있든 무조건 맨 아래로 스크롤합니다.
    if (isNewUserMessage) {
      scrollToBottom();
      setShowJumpButton(false);
    } 
    // 3. 'assistant' 메시지 스트리밍 중이거나 다른 경우
    else {
      if (isAtBottom) {
        // 사용자가 이미 맨 아래에 있다면, 계속 자동 스크롤합니다.
        scrollToBottom();
        setShowJumpButton(false);
      } else if (messages.length > previousLength.current) {
        // 사용자가 스크롤을 위로 올려 다른 내용을 보고 있다면, 자동 스크롤 대신 버튼만 표시합니다.
        setShowJumpButton(true);
      }
    }

    // 현재 메시지 길이를 다음 렌더링을 위해 저장합니다.
    previousLength.current = messages.length;
  }, [messages, isAtBottom]); // messages 또는 isAtBottom 상태가 변경될 때마다 실행됩니다.


  // `useMemo`를 사용하여 `messages` 배열이 변경될 때만 `visibleMessages`를 다시 계산합니다.
  // 이는 불필요한 렌더링을 방지하는 성능 최적화 기법입니다.
  const visibleMessages = useMemo(() => {
    return messages.length <= MAX_VISIBLE_MESSAGES
      ? messages
      : messages.slice(-MAX_VISIBLE_MESSAGES);
  }, [messages]);

  // 화면에 표시되지 않고 숨겨진 메시지의 개수
  const hiddenCount = Math.max(0, messages.length - visibleMessages.length);

  /** RAG 출처(Source)를 클릭했을 때 모달을 여는 핸들러입니다. */
  const handleSourceClick = (src: string) => {
    setSelectedSource(src);
    setShowSourceModal(true);
  };

  /** 출처 정보 모달을 닫는 핸들러입니다. */
  const handleCloseSourceModal = () => {
    setShowSourceModal(false);
    setSelectedSource(null);
  };

  return (
    <div className="message-list" ref={containerRef}>
      {/* 오래된 메시지가 숨겨져 있을 경우 알림을 표시합니다. */}
      {hiddenCount > 0 && (
        <article className="message system">
          <div className="bubble">
            <p>최근 {MAX_VISIBLE_MESSAGES}개의 메시지만 표시 중입니다.</p>
            <small className="muted">
              전체 기록이 필요하면 새 대화를 시작하거나 히스토리를 다시 불러오세요.
            </small>
          </div>
        </article>
      )}

      {/* 메시지가 없을 경우 '빈 상태' 컴포넌트를 렌더링합니다. */}
      {visibleMessages.length === 0 && hiddenCount === 0 ? (
        <EmptyChatWindow />
      ) : (
        // 메시지 목록을 순회하며 각 메시지를 렌더링합니다.
        visibleMessages.map((msg) => (
          <article key={msg.id} className={`message ${msg.role}`}>
            <div className="bubble">
              {/* `toolCall` 객체가 있으면 ToolCallWidget을, 없으면 일반 텍스트를 렌더링합니다. */}
              {msg.toolCall ? (
                <ToolCallWidget toolCall={msg.toolCall} />
              ) : (
                <ReactMarkdown components={markdownComponents}>
                  {msg.content}
                </ReactMarkdown>
              )}

              {/* RAG 출처(Source)가 있는 경우, 알약(pill) 형태로 표시합니다. */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="message-sources">
                  {msg.sources.map((src, idx) => (
                    <span
                      key={`${src.display_name}-${idx}`}
                      className="source-pill"
                      onClick={() => handleSourceClick(src.display_name)}
                    >
                      {src.display_name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </article>
        ))
      )}

      {/* '최신 메시지 보기' 버튼 (필요할 때만 표시) */}
      {showJumpButton && (
        <button className="message-scroll-indicator" onClick={scrollToBottom}>
          최신 메시지 보기
        </button>
      )}

      {/* 출처 정보 상세 모달 */}
      {showSourceModal && (
        <Modal isOpen={showSourceModal} onClose={handleCloseSourceModal}>
          <h2>소스 상세 정보</h2>
          <pre className="source-modal-content">{selectedSource}</pre>
          <button onClick={handleCloseSourceModal}>닫기</button>
        </Modal>
      )}
    </div>
  );
}
