import { useCallback, useRef, useState, useEffect } from "react";
import { notify } from "../components/NotificationHost";
import { apiRequest } from "../lib/apiClient";
import { getApiBaseUrl } from "./useEnvironment";

const API_BASE = getApiBaseUrl();

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { display_name: string }[];
};

type ApiHistoryMessage = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type ApiChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type PendingRequest = {
  query: string;
  top_k: number;
  doc_ids_filter: string[] | null;
  chat_history: ApiChatMessage[];
  session_id: string | null;
};

export function useChatSession(token: string, docFilter: string | null, sessionId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // sessionId가 없으면(예: '새 대화' 직후) 비우고 종료합니다.
    if (!sessionId) {
      setMessages([]);
      sourceRef.current?.close();
      setLoading(false);
      return;
    }

    // sessionId가 있으면, 히스토리 로딩을 시작합니다.
    setLoading(true);
    sourceRef.current?.close(); // 진행 중인 스트리밍 중단

    const fetchHistory = async () => {
      try {
        const data = await apiRequest<{ messages: ApiHistoryMessage[] }>(
          `/chat/history/${sessionId}`,
          {
            token,
            errorMessage: "대화 기록을 불러오지 못했습니다.",
          },
        );
                
        const mappedMessages: Message[] = data.messages.map((msg, index) => ({
          id: `hist-${sessionId}-${index}`, // React key를 위한 고유 ID 생성
          role: msg.role,
          content: msg.content,          
        }));

        setMessages(mappedMessages); // 불러온 메시지로 상태를 설정
        
      } catch (err) {
        notify(err instanceof Error ? err.message : "기록 로딩 실패");
        setMessages([]); // 오류 발생 시 비움
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
    
  }, [sessionId, token]);

  const sendMessage = useCallback(
    async (payload: { query: string; docFilter?: string }) => {
      if (!payload.query.trim()) return;
      if (!sessionId) {
        notify("새 대화를 시작한 후 질문해주세요");
        return;
      }

      const historyForApi: ApiChatMessage[] = messages.map(msg => ({
          role: msg.role,
          content: msg.content
      }));

      const pending: PendingRequest = {
        query: payload.query,
        top_k: 3,
        doc_ids_filter: payload.docFilter ? [payload.docFilter] : null,
        chat_history: historyForApi,
        session_id: sessionId,
      };
      const outgoing: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: payload.query,
      };
      setMessages((prev) => [...prev, outgoing]);
      streamQuery(token, pending, {
        onToken: (tokenChunk) =>
          setMessages((prev) => updateAssistant(prev, tokenChunk)),
        onSources: (sources) =>
          setMessages((prev) => attachSources(prev, sources)),
        onError: (errorMsg) => notify(errorMsg),
        onStart: () => setLoading(true),
        onFinish: () => setLoading(false),
        ref: sourceRef,
      });
    },
    [token, sessionId, docFilter, messages],
  );

  return { messages, sendMessage, loading };
}

function updateAssistant(messages: Message[], chunk: string) {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") {
    const newMsg: Message = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: chunk,
    };
    return [...messages, newMsg];
  }
  const updated = [...messages];
  updated[updated.length - 1] = {
    ...last,
    content: last.content + chunk,
  };
  return updated;
}

function attachSources(messages: Message[], sources: { display_name: string }[]) {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") return messages;
  const updated = [...messages];
  updated[updated.length - 1] = { ...last, sources };
  return updated;
}

type StreamHandlers = {
  onToken: (token: string) => void;
  onSources: (sources: { display_name: string }[]) => void;
  onError: (msg: string) => void;
  onStart: () => void;
  onFinish: () => void;
  ref: React.MutableRefObject<EventSource | null>;
};

function streamQuery(
  token: string,
  body: PendingRequest,
  handlers: StreamHandlers,
) {
  handlers.ref.current?.close();
  const url = new URL(`${API_BASE}/chat/query-stream`);
  url.searchParams.set("token", token);
  url.searchParams.set("query_request", JSON.stringify(body));

  const source = new EventSource(url.toString(), { withCredentials: false });
  handlers.ref.current = source;
  handlers.onStart();
  let ended = false;
  let hadData = false;

  source.onmessage = (event) => {
    if (!event.data) return;
    const payload = JSON.parse(event.data);
    console.log("SSE payload", payload);
    if (payload.event === "token") {
      hadData = true;
      handlers.onToken(payload.data);
    } else if (payload.event === "sources") {
      hadData = true;
      handlers.onSources(payload.data);
    } else if (payload.event === "end") {
      hadData = true;
      ended = true;
      handlers.onFinish();
      source.close();
    }
  };

  source.onerror = (error) => {
    console.error("EventSource error", {
      ended,
      hadData,
      readyState: source.readyState,
      error,
    });
    if (!ended && !hadData && source.readyState !== EventSource.CLOSED) {
      handlers.onError("스트리밍 연결이 끊어졌습니다.");
      handlers.onFinish();
    }
    source.close();
  };
}
