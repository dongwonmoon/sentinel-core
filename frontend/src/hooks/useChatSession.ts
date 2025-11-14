import { useCallback, useRef, useState } from "react";
import { notify } from "../components/NotificationHost";

import { getApiBaseUrl } from "./useEnvironment";

const API_BASE = getApiBaseUrl();

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { display_name: string }[];
};

type PendingRequest = {
  query: string;
  top_k: number;
  doc_ids_filter: string[] | null;
  chat_history: Message[];
};

export function useChatSession(token: string, docFilter: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  const sendMessage = useCallback(
    async (payload: { query: string; docFilter?: string }) => {
      if (!payload.query.trim()) return;
      const pending: PendingRequest = {
        query: payload.query,
        top_k: 3,
        doc_ids_filter: payload.docFilter ? [payload.docFilter] : null,
        chat_history: [],
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
    [token],
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
