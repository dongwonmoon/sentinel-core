/**
 * @file 단일 채팅 세션의 전체 상태와 로직을 관리하는 핵심 React Hook을 정의합니다.
 * @description 이 훅은 채팅 UI의 "두뇌" 역할을 하며, 메시지 목록 관리,
 * 대화 기록 로딩, 파일 첨부, 서버와의 실시간 스트리밍 통신 등
 * 채팅과 관련된 모든 복잡한 상호작용을 캡슐화합니다.
 */

import { useCallback, useRef, useState, useEffect } from "react";
import { notify } from "../components/NotificationHost";
import { apiRequest } from "../lib/apiClient";
import { getApiBaseUrl } from "./useEnvironment";
import { useTaskPolling, TaskStatusResponse } from "./useTaskPolling";

const API_BASE = getApiBaseUrl();

/**
 * 채팅 메시지 하나를 나타내는 타입.
 * UI 렌더링에 필요한 모든 정보를 포함합니다.
 */
export type Message = {
  /** React 리스트 렌더링 시 key로 사용될 고유 ID */
  id: string;
  /** 메시지 작성 주체 ('user' 또는 'assistant') */
  role: "user" | "assistant";
  /** 메시지의 텍스트 내용 */
  content: string;
  /** RAG 사용 시 참조한 소스 문서 정보 */
  sources?: { display_name: string }[];
  /** 어시스턴트가 도구를 사용하는 과정을 시각화하기 위한 정보 */
  toolCall?: {
    /** 실행된 도구의 이름 (예: 'RAG', 'WebSearch') */
    name: string;
    /** 도구 실행 상태 ('running': 실행 중, 'completed': 완료) */
    status: "running" | "completed";
  };
};

/** 백엔드 API에서 사용하는 대화 기록 메시지 타입 */
type ApiHistoryMessage = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

/**
 * 현재 세션에 임시로 첨부된 파일의 상태를 나타내는 타입.
 */
export type SessionAttachment = {
  /** DB에 저장된 첨부파일의 고유 ID */
  attachment_id: number;
  user_id?: number;
  /** 원본 파일 이름 */
  filename: string;
  /** 파일의 현재 상태 (인덱싱 중, 임시 사용 가능, 승인 대기 등) */
  status: "indexing" | "temporary" | "pending_review" | "promoted" | "failed";
  /** 백그라운드 인덱싱 작업의 상태를 폴링하기 위한 Celery 태스크 ID */
  task_id: string;
  /** (거버넌스) 영구 KB로 승격 요청 시 사용자가 입력한 메타데이터 */
  pending_review_metadata?: {
    suggested_kb_doc_id: string;
    note_to_admin: string;
  };
};

/**
 * 단일 채팅 세션의 전체 상태와 로직을 관리하는 핵심 React Hook입니다.
 *
 * @param token - 인증에 사용될 JWT 토큰.
 * @param sessionId - 현재 활성화된 채팅 세션의 ID. `null`일 경우 새 대화 상태를 의미합니다.
 * @returns 채팅 UI를 렌더링하고 상호작용하는 데 필요한 모든 상태와 함수.
 */
export function useChatSession(token: string, sessionId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [attachments, setAttachments] = useState<SessionAttachment[]>([]);
  // 스트리밍 요청을 중간에 취소하기 위한 AbortController 참조.
  const abortControllerRef = useRef<AbortController | null>(null);

  // sessionId가 변경될 때마다 실행되는 Effect.
  // 새로운 세션으로 전환될 때 이전 상태를 정리하고 새 대화 기록을 불러옵니다.
  useEffect(() => {
    // 1. sessionId가 없으면(예: '새 대화' 클릭 직후) 모든 상태를 초기화하고 종료.
    if (!sessionId) {
      setMessages([]);
      setAttachments([]);
      abortControllerRef.current?.abort(); // 진행 중인 스트리밍이 있었다면 중단
      setLoading(false);
      return;
    }

    // 2. 새 세션 로딩 시작: 상태 초기화 및 로딩 상태 활성화
    setLoading(true);
    setMessages([]);
    setAttachments([]);
    abortControllerRef.current?.abort(); // 이전 세션의 스트리밍 요청이 있었다면 중단

    // 3. 새 sessionId에 대한 대화 기록 비동기 로딩
    const fetchHistory = async () => {
      try {
        const data = await apiRequest<{ messages: ApiHistoryMessage[] }>(
          `/chat/history/${sessionId}`,
          {
            token,
            errorMessage: "대화 기록을 불러오지 못했습니다.",
          }
        );

        // API 응답을 UI에 맞는 Message 타입으로 변환
        const mappedMessages: Message[] = data.messages.map((msg, index) => ({
          id: `hist-${sessionId}-${index}`, // React key를 위한 고유 ID 생성
          role: msg.role,
          content: msg.content,
        }));

        setMessages(mappedMessages);
      } catch (err) {
        notify(err instanceof Error ? err.message : "기록 로딩 실패");
        setMessages([]); // 오류 발생 시 메시지 목록을 비워 사용자에게 명확한 피드백 제공
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();

    // 4. Cleanup 함수: 컴포넌트가 언마운트되거나 sessionId가 변경되기 직전에 호출됩니다.
    // 진행 중일 수 있는 스트리밍 요청을 취소하여 메모리 누수 및 불필요한 네트워크 요청을 방지합니다.
    return () => {
      abortControllerRef.current?.abort();
    };
  }, [sessionId, token]);

  // 파일 인덱싱과 같은 백그라운드 작업의 상태를 폴링(polling)하기 위한 훅.
  // 폴링은 작업이 완료될 때까지 주기적으로 서버에 상태를 물어보는 기법입니다.
  const { startPolling } = useTaskPolling({
    token,
    buildStatusPath: (taskId) => `/documents/task-status/${taskId}`,
    onSuccess: (response: TaskStatusResponse, taskId: string) => {
      notify(extractResultMessage(response, "파일 인덱싱 완료!"));
      // 인덱싱 성공 시, 해당 attachment의 상태를 'temporary'(임시 RAG 준비 완료)로 변경.
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

  /**
   * 사용자가 파일을 첨부했을 때 호출되는 함수.
   * 파일을 서버에 업로드하고, 반환된 task_id로 인덱싱 상태 폴링을 시작합니다.
   * '낙관적 UI 업데이트' 패턴을 사용하여 사용자 경험을 향상시킵니다.
   */
  const handleAttachFile = useCallback(
    async (file: File) => {
      if (!sessionId) {
        notify("새 대화를 시작한 후 파일을 첨부해주세요.");
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      // 1. [낙관적 UI 업데이트]
      //    API 요청이 성공하기 전에 먼저 UI에 'indexing' 상태로 파일을 즉시 표시합니다.
      //    사용자는 파일이 즉시 처리되기 시작하는 것처럼 느끼게 됩니다.
      const tempTaskId = `temp-id-${Date.now()}`;
      const tempAttachment: SessionAttachment = {
        attachment_id: 0, // 아직 서버로부터 ID를 받지 못함
        filename: file.name,
        status: "indexing",
        task_id: tempTaskId,
      };
      setAttachments((prev) => [...prev, tempAttachment]);

      try {
        // 2. 서버에 파일 업로드 요청
        const result = await apiRequest<{
          task_id: string;
          attachment_id: number;
        }>(`/chat/sessions/${sessionId}/attach`, {
          method: "POST",
          token,
          body: formData,
          errorMessage: "파일 첨부 실패",
        });

        // 3. 성공 시 상태 동기화
        //    API 응답 성공 후, 임시 ID를 서버가 내려준 실제 ID로 교체합니다.
        setAttachments((prev) =>
          prev.map((att) =>
            att.task_id === tempTaskId
              ? {
                  ...att,
                  task_id: result.task_id,
                  attachment_id: result.attachment_id,
                }
              : att
          )
        );

        // 4. 실제 인덱싱 상태 폴링 시작
        startPolling(result.task_id);
      } catch (err) {
        notify(err instanceof Error ? err.message : "파일 업로드 오류");
        // 5. 실패 시 롤백
        //    실패 시, 낙관적 UI 업데이트로 추가했던 임시 attachment를 제거합니다.
        setAttachments((prev) =>
          prev.filter((att) => att.task_id !== tempTaskId)
        );
      }
    },
    [sessionId, token, startPolling]
  );

  /**
   * (거버넌스) 임시 첨부 파일을 영구 지식 베이스(KB)로 등록해달라고 관리자에게 요청합니다.
   */
  const handleRequestPromotion = useCallback(
    async (
      attachmentId: number,
      metadata: { suggested_kb_doc_id: string; note_to_admin: string }
    ) => {
      if (!token) return;

      try {
        await apiRequest(`/documents/request_promotion/${attachmentId}`, {
          method: "POST",
          token,
          json: metadata,
          errorMessage: "승격 요청 실패",
        });
        notify("관리자에게 KB 등록 요청을 보냈습니다.");
        // 요청 성공 시, UI 상태를 'pending_review'(승인 대기중)으로 변경합니다.
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
    },
    [token]
  );

  /**
   * 사용자가 메시지를 전송할 때 호출되는 메인 함수.
   * 서버에 쿼리를 보내고 응답 스트리밍 처리를 `streamQuery` 함수에 위임합니다.
   */
  const sendMessage = useCallback(
    async (payload: { query: string }) => {
      if (!payload.query.trim()) return;
      if (!sessionId) {
        notify("새 대화를 시작한 후 질문해주세요");
        return;
      }

      // 사용자 메시지를 즉시 UI에 추가 (낙관적 업데이트)
      const outgoing: Message = {
        id: `user-${crypto.randomUUID()}`,
        role: "user",
        content: payload.query,
      };
      setMessages((prev) => [...prev, outgoing]);

      const requestBody = {
        query: payload.query,
        top_k: 3,
        session_id: sessionId,
      };

      // `streamQuery` 함수를 호출하여 SSE 스트리밍 시작
      streamQuery(token, requestBody, {
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
        ref: abortControllerRef,
      });
    },
    [token, sessionId] // messages는 의존성 배열에서 제거하여, 스트리밍 중 메시지 상태가 변해도 sendMessage 함수가 재생성되지 않도록 함
  );

  return {
    messages,
    sendMessage,
    loading,
    attachments,
    handleAttachFile,
    handleRequestPromotion,
  };
}

// --- 메시지 목록 상태 업데이트 헬퍼 함수들 ---
// 이 함수들은 모두 순수 함수(Pure Function)로, 불변성(immutability)을 유지하기 위해
// 항상 새로운 메시지 배열을 생성하여 반환합니다. 이는 React의 상태 관리 원칙에 부합합니다.

/**
 * 스트리밍된 'token' 이벤트를 처리하여 어시스턴트 메시지를 업데이트합니다.
 * @param messages - 현재 메시지 배열.
 * @param tokenPayload - SSE로 받은 토큰 데이터. `new_message` 플래그를 포함.
 * @returns 새로운 메시지 배열.
 */
function updateAssistant(
  messages: Message[],
  tokenPayload: { chunk: string; new_message: boolean }
): Message[] {
  const last = messages[messages.length - 1];

  // 새 어시스턴트 메시지 버블을 시작해야 하는 경우:
  // 1. 마지막 메시지가 없거나,
  // 2. 마지막 메시지가 'user'의 메시지이거나,
  // 3. 마지막 메시지가 'toolCall' 위젯이거나,
  // 4. 서버에서 `new_message: true` 플래그를 보낸 경우 (예: 도구 사용 후 첫 토큰)
  if (
    !last ||
    last.role !== "assistant" ||
    last.toolCall ||
    tokenPayload.new_message
  ) {
    const newMsg: Message = {
      id: `assistant-${crypto.randomUUID()}`,
      role: "assistant",
      content: tokenPayload.chunk,
    };
    return [...messages, newMsg];
  }

  // 그 외의 경우, 마지막 어시스턴트 메시지에 토큰 내용을 이어 붙입니다.
  const updated = [...messages];
  updated[updated.length - 1] = {
    ...last,
    content: last.content + tokenPayload.chunk,
  };
  return updated;
}

/**
 * 'tool_start' 이벤트를 처리하여 '도구 사용 중' 위젯을 추가하거나 업데이트합니다.
 */
function addOrUpdateToolCall(messages: Message[], toolName: string): Message[] {
  const last = messages[messages.length - 1];

  // 마지막 메시지가 이미 '실행 중인 도구' 위젯이라면, 텍스트만 업데이트.
  // (예: RAG -> WebSearch로 연속 실행 시)
  if (last && last.role === "assistant" && last.toolCall?.status === "running") {
    const updated = [...messages];
    updated[updated.length - 1] = {
      ...last,
      toolCall: { ...last.toolCall, name: toolName },
    };
    return updated;
  }

  // 아니라면 새 '도구 호출' 메시지 버블을 추가합니다.
  const newMsg: Message = {
    id: `assistant-tool-${crypto.randomUUID()}`,
    role: "assistant",
    content: "", // 도구 호출 메시지는 content가 비어있습니다.
    toolCall: {
      name: toolName,
      status: "running",
    },
  };
  return [...messages, newMsg];
}

/**
 * 'tool_end' 이벤트를 처리하여 '도구 사용 중' 위젯의 상태를 'completed'로 변경합니다.
 */
function completeToolCall(messages: Message[], toolName: string): Message[] {
  const last = messages[messages.length - 1];

  if (last && last.role === "assistant" && last.toolCall?.name === toolName) {
    const updated = [...messages];
    updated[updated.length - 1] = {
      ...last,
      toolCall: { ...last.toolCall, status: "completed" },
    };
    return updated;
  }
  return messages;
}

/**
 * 'sources' 이벤트를 처리하여 마지막 어시스턴트 메시지에 RAG 출처 정보를 첨부합니다.
 */
function attachSources(
  messages: Message[],
  sources: { display_name: string }[]
): Message[] {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") return messages;

  const updated = [...messages];
  updated[updated.length - 1] = { ...last, sources };
  return updated;
}

type StreamHandlers = {
  onToken: (payload: { chunk: string; new_message: boolean }) => void;
  onToolStart: (toolName: string) => void;
  onToolEnd: (toolName: string) => void;
  onSources: (sources: { display_name: string }[]) => void;
  onError: (msg: string) => void;
  onStart: () => void;
  onFinish: () => void;
  ref: React.MutableRefObject<AbortController | null>;
};

/**
 * `fetch` API와 `ReadableStream`을 사용하여 SSE(Server-Sent Events)를 수동으로 처리하는 함수.
 *
 * @remarks
 * 네이티브 `EventSource` API 대신 `fetch`를 사용하는 이유:
 * 1.  **POST 요청**: `EventSource`는 GET 요청만 지원하는 반면, 채팅 쿼리는 복잡한 데이터를
 *     포함하므로 POST 요청이 더 적합합니다.
 * 2.  **헤더 제어**: `Authorization` 같은 커스텀 헤더를 쉽게 추가할 수 있습니다.
 * 3.  **에러 처리**: `fetch`는 HTTP 에러 상태(4xx, 5xx)를 더 명시적으로 처리할 수 있습니다.
 * 4.  **요청 중단**: `AbortController`를 통해 스트리밍 요청을 안정적으로 중단할 수 있습니다.
 *
 * @param token - 인증 토큰.
 * @param body - 서버로 보낼 요청 본문.
 * @param handlers - SSE 이벤트 종류에 따라 실행될 콜백 함수들의 묶음.
 */
async function streamQuery(
  token: string,
  body: { query: string; session_id: string },
  handlers: StreamHandlers
) {
  // 이전 요청이 있었다면 중단하여, 동시 스트리밍을 방지합니다.
  handlers.ref.current?.abort();

  const controller = new AbortController();
  handlers.ref.current = controller;

  handlers.onStart();
  let ended = false;
  let accumulatedChunks = ""; // SSE 데이터는 분할되어 도착할 수 있으므로, 이를 누적하기 위한 변수.

  try {
    const response = await fetch(`${API_BASE}/chat/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`스트리밍 요청 실패 (${response.status}): ${errorText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("스트림 리더를 가져올 수 없습니다.");

    const decoder = new TextDecoder("utf-8");

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      accumulatedChunks += chunk;

      // SSE 메시지 형식은 "data: {...}\n\n" 이므로, "\n\n"을 기준으로 파싱합니다.
      const lines = accumulatedChunks.split("\n\n");

      // 마지막 라인은 완전한 메시지가 아닐 수 있으므로, 다음 청크 처리를 위해 남겨둡니다.
      accumulatedChunks = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.substring(6);
          try {
            const payload = JSON.parse(data);

            // 이벤트 종류에 따라 적절한 핸들러를 호출합니다.
            if (payload.event === "token") {
              handlers.onToken(payload.data);
            } else if (payload.event === "sources") {
              handlers.onSources(payload.data);
            } else if (payload.event === "end") {
              ended = true;
              handlers.onFinish(); // 'end' 이벤트를 받으면 즉시 onFinish 호출
            } else if (payload.event === "tool_start") {
              handlers.onToolStart(payload.data.name);
            } else if (payload.event === "tool_end") {
              handlers.onToolEnd(payload.data.name);
            } else if (payload.event === "error") {
              handlers.onError(payload.data);
              ended = true;
            }
          } catch (e) {
            console.error("SSE 데이터 파싱 실패:", data, e);
          }
        }
      }
      if (ended) break;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      console.log("스트리밍이 사용자에 의해 중단되었습니다.");
    } else {
      console.error("스트리밍 처리 중 오류 발생:", error);
      handlers.onError(
        error instanceof Error ? error.message : "스트리밍 연결이 끊어졌습니다."
      );
    }
  } finally {
    // `finally` 블록은 스트림이 정상적으로('end' 이벤트) 또는 비정상적으로
    // (에러, 중단) 종료되었을 때 항상 실행됩니다.
    if (!ended) handlers.onFinish(); // 'end' 이벤트 없이 종료된 경우를 대비해 로딩 상태를 확실히 해제
    handlers.ref.current = null; // 컨트롤러 참조 정리
  }
}

/**
 * Celery 태스크 폴링 응답에서 사용자에게 보여줄 메시지를 추출하는 헬퍼 함수.
 */
function extractResultMessage(
  response: TaskStatusResponse,
  fallback: string
): string {
  if (!response.result) return fallback;
  if (typeof response.result === "string") return response.result;
  // response.result가 객체일 경우 message 속성을 찾습니다.
  if (
    response.result &&
    typeof response.result === "object" &&
    "message" in response.result
  ) {
    return String(response.result.message);
  }
  return fallback;
}
