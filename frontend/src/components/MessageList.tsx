import { useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "../hooks/useChatSession";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import Modal from "./Modal";
import EmptyChatWindow from "./EmptyChatWindow";

type Props = {

  messages: Message[];

  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;

};



const MAX_VISIBLE_MESSAGES = 150;



const MemoizedSyntaxHighlighter = ({ children, className, ...props }: any) => {

  const match = /language-(\w+)/.exec(className || "");

  const codeContent = String(children).replace(/\n$/, "");



  const handleCopyClick = async () => {

    try {

      await navigator.clipboard.writeText(codeContent);

      // Optionally, add a visual feedback like a "Copied!" tooltip

      console.log("Code copied to clipboard!");

    } catch (err) {

      console.error("Failed to copy code: ", err);

    }

  };



  return match ? (

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

  ) : (

    <code className={className} {...props}>

      {children}

    </code>

  );

};



const components = {

  code({ node, inline, className, children, ...props }: any) {

    if (inline) {

      return (

        <code className={className} {...props}>

          {children}

        </code>

      );

    }

    return (

      <MemoizedSyntaxHighlighter

        className={className}

        children={children}

        {...props}

      />

    );

  },

};



export default function MessageList({ messages, sendMessage }: Props) {

  const containerRef = useRef<HTMLDivElement>(null);

  const [isAtBottom, setIsAtBottom] = useState(true);

  const [showJumpButton, setShowJumpButton] = useState(false);

  const previousLength = useRef(0);



  const [showSourceModal, setShowSourceModal] = useState(false);

  const [selectedSource, setSelectedSource] = useState<string | null>(null);



  const handleSourceClick = (sourceName: string) => {

    setSelectedSource(sourceName);

    setShowSourceModal(true);

  };



  const handleCloseSourceModal = () => {

    setShowSourceModal(false);

    setSelectedSource(null);

  };



  const handleRegenerate = () => {

    const lastUserMessage = messages

      .slice()

      .reverse()

      .find((msg) => msg.role === "user");

    if (lastUserMessage) {

      sendMessage({ query: lastUserMessage.content });

    }

  };



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



            {visibleMessages.length === 0 && hiddenCount === 0 ? (



              <EmptyChatWindow />



            ) : (



              visibleMessages.map((msg) => (



                <article key={msg.id} className={`message ${msg.role}`}>



                  <div className="bubble">



                    <ReactMarkdown components={components}>{msg.content}</ReactMarkdown>



                    {msg.role === "assistant" && (



                      <button



                        onClick={() => navigator.clipboard.writeText(msg.content)}



                        className="copy-message-button"



                        title="메시지 복사"



                      >



                        📋



                      </button>



                    )}



                    {msg.role === "user" && (



                      <button



                        onClick={handleRegenerate}



                        className="regenerate-message-button"



                        title="메시지 재생성"



                      >



                        🔄



                      </button>



                    )}



                    {msg.sources && msg.sources.length > 0 && (



                      <div className="message-sources">



                        {msg.sources.map((src, index) => (



                          <span



                            key={`${src.display_name}-${index}`}



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



      {showJumpButton && (

        <button className="message-scroll-indicator" onClick={scrollToBottom}>

          최신 메시지 보기

        </button>

      )}



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
