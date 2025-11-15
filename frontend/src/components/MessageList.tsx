import { useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "../hooks/useChatSession";

type Props = {
  messages: Message[];
};

const MAX_VISIBLE_MESSAGES = 150;

export default function MessageList({ messages }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showJumpButton, setShowJumpButton] = useState(false);
  const previousLength = useRef(0);

  const visibleMessages = useMemo(() => {
    if (messages.length <= MAX_VISIBLE_MESSAGES) {
      return messages;
    }
    return messages.slice(-MAX_VISIBLE_MESSAGES);
  }, [messages]);

  const hiddenCount = Math.max(0, messages.length - visibleMessages.length);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;
    const handleScroll = () => {
      const threshold = 48;
      const nearBottom =
        node.scrollHeight - node.scrollTop - node.clientHeight < threshold;
      setIsAtBottom(nearBottom);
    };
    node.addEventListener("scroll", handleScroll);
    handleScroll();
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToBottom = () => {
    const node = containerRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  };

  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
      setShowJumpButton(false);
    } else if (messages.length > previousLength.current) {
      setShowJumpButton(true);
    }
    previousLength.current = messages.length;
  }, [messages, isAtBottom]);

  return (
    <div className="message-list" ref={containerRef}>
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

      {visibleMessages.map((msg) => (
        <article key={msg.id} className={`message ${msg.role}`}>
          <div className="bubble">
            <p>{msg.content}</p>
            {msg.sources && msg.sources.length > 0 && (
              <details className="sources" open={msg.sources.length <= 2}>
                <summary>출처 {msg.sources.length}건</summary>
                <ul>
                  {msg.sources.map((src, index) => (
                    <li key={`${src.display_name}-${index}`}>{src.display_name}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </article>
      ))}

      {showJumpButton && (
        <button className="message-scroll-indicator" onClick={scrollToBottom}>
          최신 메시지 보기
        </button>
      )}
    </div>
  );
}
