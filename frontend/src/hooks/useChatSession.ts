import { useCallback, useRef, useState, useEffect } from "react";
import { notify } from "../components/NotificationHost";
import { apiRequest } from "../lib/apiClient";
import { getApiBaseUrl } from "./useEnvironment";
import { useTaskPolling, TaskStatusResponse } from "./useTaskPolling";

const API_BASE = getApiBaseUrl();

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { display_name: string }[];
  toolCall?: {
    name: string;
    status: "running" | "completed";
  }
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
  // doc_ids_filter: string[] | null;
  // chat_history: ApiChatMessage[];
  session_id: string | null;
};

export type SessionAttachment = {
  attachment_id: number;
  filename: string;
  status: "indexing" | "temporary" | "pending_review" | "promoted" | "failed";
  task_id: string; // 폴링을 위한 ID
  pending_review_metadata?: {
    suggested_kb_doc_id: string;
    note_to_admin: string;
  };
};

export function useChatSession(token: string, docFilter: string | null, sessionId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const [attachments, setAttachments] = useState<SessionAttachment[]>([]);

  useEffect(() => {
    // sessionId가 없으면(예: '새 대화' 직후) 비우고 종료합니다.
    if (!sessionId) {
      setMessages([]);
      setAttachments([]);
      sourceRef.current?.close();
      setLoading(false);
      return;
    }

    // sessionId가 있으면, 히스토리 로딩을 시작합니다.
    setLoading(true);
    setAttachments([]);
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

  const { startPolling } = useTaskPolling({
    token,
    buildStatusPath: (taskId) => `/documents/task-status/${taskId}`,
    onSuccess: (response: TaskStatusResponse, taskId: string) => {
      notify(extractResultMessage(response, "파일 인덱싱 완료!"));
      // 인덱싱 성공 시, attachment 상태를 'temporary'(임시 RAG 준비 완료)로 변경
      setAttachments((prev) =>
        prev.map((att) =>
          att.task_id === taskId ? { ...att, status: "temporary" } : att
        )
      );
    },
    onFailure: (response: TaskStatusResponse, taskId: string) => {
      notify(extractResultMessage(response, "파일 인덱싱 실패"));
      setAttachments((prev) =>
        prev.map((att) =>
          att.task_id === taskId ? { ...att, status: "failed" } : att
        )
      );
    },
    onError: (err: Error, taskId: string) => {
      notify(err.message);
      setAttachments((prev) =>
        prev.map((att) =>
          att.task_id === taskId ? { ...att, status: "failed" } : att
        )
      );
    },
  });

  const handleAttachFile = useCallback(
    async (file: File) => {
      if (!sessionId) {
        notify("새 대화를 시작한 후 파일을 첨부해주세요.");
        return;
      }
      
      const formData = new FormData();
      formData.append("file", file);

      // (로컬에 임시로 'indexing' 상태 추가)
      const tempTaskId = `temp-id-${Date.now()}`;
      const tempAttachment: SessionAttachment = {
        attachment_id: 0, // 아직 모름
        filename: file.name,
        status: "indexing",
        task_id: tempTaskId,
      };
      setAttachments((prev) => [...prev, tempAttachment]);

      try {
        const result = await apiRequest<{ 
          task_id: string; 
          attachment_id: number; 
        }>(
          `/chat/sessions/${sessionId}/attach`,
          {
            method: "POST",
            token,
            body: formData,
            errorMessage: "파일 첨부 실패",
          }
        );

        // (API 응답 후, 실제 task_id로 업데이트)
        setAttachments((prev) =>
          prev.map((att) =>
            att.task_id === tempTaskId
              ? { ...att, task_id: result.task_id, attachment_id: result.attachment_id }
              : att
          )
        );
        
        // [핵심] 실제 Polling 시작
        startPolling(result.task_id);

      } catch (err) {
        notify(err instanceof Error ? err.message : "파일 업로드 오류");
        // (실패 시 임시 attachment 제거)
        setAttachments((prev) => prev.filter((att) => att.task_id !== tempTaskId));
      }
    },
    [sessionId, token, startPolling]
  );

  const handleRequestPromotion = useCallback(
    async (attachmentId: number, metadata: { suggested_kb_doc_id: string; note_to_admin: string }) => {
      if (!token) return;
      
      try {
        await apiRequest(
          `/documents/request_promotion/${attachmentId}`,
          {
            method: "POST",
            token,
            json: metadata,
            errorMessage: "승격 요청 실패"
          }
        );
        notify("관리자에게 KB 등록 요청을 보냈습니다.");
        // (상태를 'pending_review'로 변경)
        setAttachments((prev) =>
          prev.map((att) =>
            att.attachment_id === attachmentId
              ? { ...att, status: "pending_review", pending_review_metadata: metadata }
              : att
          )
        );
      } catch (err) {
         notify(err instanceof Error ? err.message : "요청 중 오류 발생");
      }
    }, [token]
  );

  const sendMessage = useCallback(
    async (payload: { query: string; docFilter?: string }) => {
      if (!payload.query.trim()) return;
      if (!sessionId) {
        notify("새 대화를 시작한 후 질문해주세요");
        return;
      }

      const pending: PendingRequest = {
        query: payload.query,
        top_k: 3,
        // doc_ids_filter: payload.docFilter ? [payload.docFilter] : null,
        // chat_history: historyForApi,
        session_id: sessionId,
      };
      const outgoing: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: payload.query,
      };
      setMessages((prev) => [...prev, outgoing]);
      streamQuery(token, pending, {
        onToken: (tokenPayload) =>
          setMessages((prev) => updateAssistant(prev, tokenPayload)),
        onToolStart: (toolName) =>
          setMessages((prev) => addOrUpdateToolCall(prev, toolName)),
        onToolEnd: (toolName) =>
          setMessages((prev) => completeToolCall(prev, toolName)),
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

  return { messages, sendMessage, loading, attachments, handleAttachFile, handleRequestPromotion, };;
}

function updateAssistant(
  messages: Message[], 
  tokenPayload: { chunk: string; new_message: boolean }
) {
  const last = messages[messages.length - 1];
  if (
    !last || 
    last.role !== "assistant" || 
    last.toolCall || 
    tokenPayload.new_message
  ) {
    const newMsg: Message = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: tokenPayload.chunk,
    };
    return [...messages, newMsg];
  }
  const updated = [...messages];
  updated[updated.length - 1] = {
    ...last,
    content: last.content + tokenPayload.chunk,
  };
  return updated;
}

function addOrUpdateToolCall(messages: Message[], toolName: string): Message[] {
  const last = messages[messages.length - 1];

  // 마지막 메시지가 이미 '실행 중인 도구' 위젯이라면, 텍스트만 업데이트
  // (예: RAG -> WebSearch로 연속 실행 시)
  if (last && last.role === "assistant" && last.toolCall?.status === "running") {
    const updated = [...messages];
    updated[updated.length - 1] = {
      ...last,
      toolCall: { ...last.toolCall, name: toolName },
    };
    return updated;
  }

  // 아니라면 새 '도구 호출' 메시지 버블 추가
  const newMsg: Message = {
    id: `assistant-tool-${Date.now()}`,
    role: "assistant",
    content: "", // 도구 호출 메시지는 content가 비어있음
    toolCall: {
      name: toolName,
      status: "running",
    },
  };
  return [...messages, newMsg];
}

function completeToolCall(messages: Message[], toolName: string): Message[] {
  const last = messages[messages.length - 1];
  
  // 마지막 메시지가 실행 중인 도구 메시지일 경우, 'completed'로 변경
  if (last && last.role === "assistant" && last.toolCall?.name === toolName) {
    const updated = [...messages];
    updated[updated.length - 1] = {
      ...last,
      toolCall: { ...last.toolCall, status: "completed" },
    };
    return updated;
  }
  return messages; // 일치하는 메시지 없으면 원본 반환
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
  onToolStart: (toolName: string) => void;
  onToolEnd: (toolName: string) => void;
  onSources: (sources: { display_name: string }[]) => void;
  onError: (msg: string) => void;
  onStart: () => void;
  onFinish: () => void;
  ref: React.MutableRefObject<EventSource | null>;
};

async function streamQuery(
  token: string,
  body: PendingRequest,
  handlers: StreamHandlers,
) {
  handlers.ref.current?.close(); // (EventSource 타입이 아니지만, AbortController로 대체 가능)
  
  // AbortController를 사용하여 요청 중단 기능 구현
  const controller = new AbortController();
  // @ts-ignore (ref 타입을 EventSource에서 AbortController로 변경)
  handlers.ref.current = controller;
  
  handlers.onStart();
  let ended = false;
  let hadData = false;
  let accumulatedChunks = ""; // 토큰 누적

  try {
    const response = await fetch(`${API_BASE}/chat/query-stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal, // 중단 신호
    });

    if (!response.ok) {
      throw new Error(
        `스트리밍 요청 실패 (${response.status} ${response.statusText})`,
      );
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("스트림 리더를 가져올 수 없습니다.");
    }

    const decoder = new TextDecoder("utf-8");

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (!ended) { // 'end' 이벤트 없이 스트림이 종료된 경우
          console.warn("Stream ended without explicit 'end' event.");
          handlers.onFinish();
        }
        break;
      }
      
      hadData = true;
      const chunk = decoder.decode(value, { stream: true });
      accumulatedChunks += chunk;

      // SSE 메시지 형식 (data: {...}\n\n)에 따라 파싱
      const lines = accumulatedChunks.split("\n\n");

      // 마지막 라인은 다음 청크를 위해 누적
      accumulatedChunks = lines.pop() || ""; 

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.substring(6);
          const payload = JSON.parse(data);

          if (payload.event === "token") {
            handlers.onToken(payload.data);
          } else if (payload.event === "sources") {
            handlers.onSources(payload.data);
          } else if (payload.event === "end") {
            ended = true;
            handlers.onFinish();
            reader.releaseLock();
            controller.abort(); // 스트림 종료
            break;
          } else if (payload.event === "tool_start") {
            handlers.onToolStart(payload.data.name);
          } else if (payload.event === "tool_end") {
            handlers.onToolEnd(payload.data.name);
          }
        }
      }
      if (ended) break;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      console.log("Stream manually aborted.");
      handlers.onFinish();
    } else {
      console.error("EventSource error", { error });
      if (!ended && !hadData) {
        handlers.onError(
          error instanceof Error ? error.message : "스트리밍 연결이 끊어졌습니다.",
        );
        handlers.onFinish();
      }
    }
  } finally {
    // @ts-ignore
    handlers.ref.current = null;
  }
}

function extractResultMessage(
  response: TaskStatusResponse,
  fallback: string,
) {
  if (!response.result) return fallback;
  if (typeof response.result === "string") return response.result;
  // @ts-ignore
  return response.result.message ?? fallback;
}