import { useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "../hooks/useChatSession";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import Modal from "./Modal";
import EmptyChatWindow from "./EmptyChatWindow";
import ToolCallWidget from "./ToolCallWidget";

type Props = {
  messages: Message[];
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
};

const MAX_VISIBLE_MESSAGES = 150;

// ======================================================
// Code Block (Markdown) Syntax Highlighter
// ======================================================

const MemoizedSyntaxHighlighter = ({ children, className, ...props }: any) => {
  const match = /language-(\w+)/.exec(className || "");
  const codeContent = String(children).replace(/\n$/, "");

  const handleCopyClick = async () => {
    try {
      await navigator.clipboard.writeText(codeContent);
      console.log("Code copied to clipboard!");
    } catch (err) {
      console.error("Failed to copy code:", err);
    }
  };

  if (!match) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match[1]}
        PreTag="div"
        {...props}
      >
        {codeContent}
      </SyntaxHighlighter>

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

const markdownComponents = {
  code({ inline, className, children, ...props }: any) {
    return inline ? (
      <code className={className} {...props}>
        {children}
      </code>
    ) : (
      <MemoizedSyntaxHighlighter className={className} {...props}>
        {children}
      </MemoizedSyntaxHighlighter>
    );
  },
};

// ======================================================
// MessageList Component
// ======================================================

export default function MessageList({ messages, sendMessage }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousLength = useRef(0);

  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showJumpButton, setShowJumpButton] = useState(false);

  const [showSourceModal, setShowSourceModal] = useState(false);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);

  // 최신 메시지 재생성
  const handleRegenerate = () => {
    const lastUserMessage = [...messages].reverse().find((msg) => msg.role === "user");
    if (lastUserMessage) {
      sendMessage({ query: lastUserMessage.content });
    }
  };

  // 하단 스크롤
  const scrollToBottom = () => {
    const node = containerRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  };

  // 스크롤 이벤트
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
    
    // 1. 방금 추가된 메시지가 'user' 메시지인지 확인합니다.
    const isNewUserMessage = lastMessage?.role === 'user' && messages.length > previousLength.current;

    // 2. 새 메시지가 'user' 타입이면, (요청대로) 무조건 맨 아래로 스크롤합니다.
    if (isNewUserMessage) {
      scrollToBottom();
      setShowJumpButton(false);
    } 
    // 3. 'assistant' 메시지이거나 스크롤 이벤트일 경우, 기존 로직을 따릅니다.
    else {
      if (isAtBottom) {
        scrollToBottom(); // 사용자가 이미 맨 아래에 있을 때만 자동 스크롤
        setShowJumpButton(false);
      } else if (messages.length > previousLength.current) {
        setShowJumpButton(true); // 사용자가 스크롤을 올렸다면, 버튼만 표시
      }
    }

    previousLength.current = messages.length;
  }, [messages, isAtBottom]); // 의존성 배열은 [messages, isAtBottom]을 유지합니다.

  // 자동 스크롤 + Jump 버튼 표시
  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
      setShowJumpButton(false);
    } else if (messages.length > previousLength.current) {
      setShowJumpButton(true);
    }

    previousLength.current = messages.length;
  }, [messages, isAtBottom]);

  // 표시할 메시지 제한
  const visibleMessages = useMemo(() => {
    return messages.length <= MAX_VISIBLE_MESSAGES
      ? messages
      : messages.slice(-MAX_VISIBLE_MESSAGES);
  }, [messages]);

  const hiddenCount = Math.max(0, messages.length - visibleMessages.length);

  // Source Modal 핸들링
  const handleSourceClick = (src: string) => {
    setSelectedSource(src);
    setShowSourceModal(true);
  };

  const handleCloseSourceModal = () => {
    setShowSourceModal(false);
    setSelectedSource(null);
  };

  return (
    <div className="message-list" ref={containerRef}>
      {/* 오래된 메시지 존재 알림 */}
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

      {/* 메시지 없을 때 */}
      {visibleMessages.length === 0 && hiddenCount === 0 ? (
        <EmptyChatWindow />
      ) : (
        visibleMessages.map((msg) => (
          <article key={msg.id} className={`message ${msg.role}`}>
            <div className="bubble">
              {/* msg.toolCall 객체가 존재하는지 확인합니다. */}
              {msg.toolCall ? (
                // 1. toolCall이 있으면 ToolCallWidget을 렌더링합니다.
                <ToolCallWidget toolCall={msg.toolCall} />
              ) : (
                // 2. toolCall이 없으면 (일반 텍스트 메시지) ReactMarkdown을 렌더링합니다.
                <ReactMarkdown components={markdownComponents}>
                  {msg.content}
                </ReactMarkdown>
              )}

              {/* 복사 버튼 */}
              {/* {msg.role === "assistant" && (
                <button
                  onClick={() => navigator.clipboard.writeText(msg.content)}
                  className="copy-message-button"
                  title="메시지 복사"
                >
                  📋
                </button>
              )} */}

              {/* 재생성 버튼 */}
              {/* {msg.role === "user" && (
                <button
                  onClick={handleRegenerate}
                  className="regenerate-message-button"
                  title="메시지 재생성"
                >
                  🔄
                </button>
              )} */}

              {/* Sources */}
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

      {/* jump-to-bottom 버튼 */}
      {showJumpButton && (
        <button className="message-scroll-indicator" onClick={scrollToBottom}>
          최신 메시지 보기
        </button>
      )}

      {/* Source Modal */}
      {showSourceModal && (
        <Modal isOpen={showSourceModal} onClose={handleCloseSourceModal}>
          <h2>소스 상세 정보</h2>
          <p>{selectedSource}</p>
          <button onClick={handleCloseSourceModal}>닫기</button>
        </Modal>
      )}
    </div>
  );
}
