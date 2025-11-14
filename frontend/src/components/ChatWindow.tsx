import { AuthResult } from "./AuthView";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { Message } from "../hooks/useChatSession";

type Props = {
  auth: AuthResult;
  documentOptions: { id: string; name: string }[];
  selectedDoc: string | null;
  onDocChange: (value: string | null) => void;
  messages: Message[];
  loading: boolean;
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
};

export default function ChatWindow({
  auth,
  documentOptions,
  selectedDoc,
  onDocChange,
  messages,
  loading,
  sendMessage,
}: Props) {
  // const session = useChatSession(auth.token, selectedDoc);

  return (
    <section className="chat-window">
      <header className="chat-header">
        <div>
          <h2>대화</h2>
          <p className="muted">
            {selectedDoc ? `필터: ${selectedDoc}` : "전체 문서를 대상으로 검색합니다."}
          </p>
        </div>
        <select
          value={selectedDoc ?? ""}
          onChange={(e) => onDocChange(e.target.value || null)}
        >
          <option value="">모든 문서</option>
          {documentOptions.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.name}
            </option>
          ))}
        </select>
      </header>
      <MessageList messages={messages} />
      <Composer
        disabled={loading}
        onSend={(text) =>
          sendMessage({
            query: text,
            docFilter: selectedDoc ?? undefined,
          })
        }
      />
    </section>
  );
}
