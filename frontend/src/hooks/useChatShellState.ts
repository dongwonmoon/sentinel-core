/**
 * @file 앱의 전역 셸(Shell) UI 상태를 관리하는 커스텀 훅입니다.
 * @description 이 훅은 애플리케이션의 여러 부분에서 공유되어야 하는 UI 상태
 * (예: 현재 활성화된 세션 ID, 선택된 문서, 활성화된 우측 패널)를 중앙에서 관리합니다.
 * @remarks 일부 상태 관리 로직(예: `activeSessionId`)은 `ChatLayout.tsx`로 이전되었을 수 있습니다.
 * 이 훅은 상태 관리 로직을 중앙화하는 패턴의 예시로 참고할 수 있습니다.
 */

import { useCallback, useState } from "react";
import { useAuth } from "../providers/AuthProvider"; 
import { apiRequest } from "../lib/apiClient"; 
import { notify } from "../components/NotificationHost"; 
import { useMutation } from "@tanstack/react-query";

/** 우측 패널에서 표시될 수 있는 탭(패널)의 ID를 정의하는 타입입니다. */
export type PanelId = "context" | "scheduler";

export function useChatShellState() {
  // --- 1. 훅 및 상태 초기화 ---
  const { token } = useAuth();

  // RAG 검색 시 필터링할 특정 문서의 ID를 관리하는 상태
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  // 현재 활성화된 채팅 세션의 ID를 관리하는 상태
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  // 우측 패널에 표시될 탭(context 또는 scheduler)을 관리하는 상태
  const [activePanel, setActivePanel] = useState<PanelId>("context");

  // --- 2. 데이터 변경 (useMutation) ---
  // `useMutation`을 사용하여 세션의 RAG 컨텍스트(문서 필터)를 업데이트합니다.
  const { mutate: updateContext } = useMutation({
    mutationFn: ({ sessionId, docFilter }: { sessionId: string; docFilter: string | null }) => {
      if (!token) throw new Error("인증되지 않았습니다.");
      // 백엔드 API를 호출하여 특정 세션의 `doc_ids_filter`를 업데이트합니다.
      return apiRequest(
        `/chat/sessions/${sessionId}/context`,
        {
          method: "PUT",
          token,
          json: { doc_ids_filter: docFilter ? [docFilter] : null },
          errorMessage: "RAG 필터 업데이트에 실패했습니다.",
        }
      );
    },
    onError: (err) => notify(err instanceof Error ? err.message : "업데이트 오류"),
  });

  // --- 3. 이벤트 핸들러 ---

  /** '새 대화' 버튼 클릭 시 호출됩니다. */
  const handleNewChat = useCallback(() => {
    const newSessionId = crypto.randomUUID();
    setActiveSessionId(newSessionId);
    setSelectedDoc(null); // 새 대화에서는 문서 필터를 초기화합니다.
    // 새 세션이 생성되었음을 백엔드에 알릴 수 있습니다 (현재는 컨텍스트 업데이트로 처리).
    if (token) {
      updateContext({ sessionId: newSessionId, docFilter: null });
    }
  }, [token, updateContext]);

  /**
   * RAG 검색 대상을 특정 문서로 제한할 때 호출됩니다.
   * @param docId 필터링할 문서의 ID. `null`이면 필터를 해제합니다.
   */
  const handleSetSelectedDoc = useCallback(
    (docId: string | null) => {
      setSelectedDoc(docId);
      // 현재 활성화된 세션이 있을 경우, 백엔드에 컨텍스트 업데이트를 요청합니다.
      if (activeSessionId && token) {
        updateContext({ sessionId: activeSessionId, docFilter: docId });
      }
    },
    [activeSessionId, token, updateContext]
  );

  /** 사이드바에서 다른 대화를 선택했을 때 호출됩니다. */
  const handleSelectConversation = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
    setSelectedDoc(null); // 다른 대화로 전환 시 문서 필터를 초기화합니다.
  }, []);

  // --- 4. 훅의 반환 값 ---
  return {
    selectedDoc,
    setSelectedDoc: handleSetSelectedDoc,
    activeSessionId,
    selectConversation: handleSelectConversation,
    activePanel,
    setActivePanel,
    handleNewChat,
  };
}
