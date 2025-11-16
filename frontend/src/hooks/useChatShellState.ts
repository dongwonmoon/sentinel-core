import { useCallback, useState } from "react";
import { useAuth } from "../providers/AuthProvider"; 
import { apiRequest } from "../lib/apiClient"; 
import { notify } from "../components/NotificationHost"; 
import { useMutation } from "@tanstack/react-query";

export type PanelId = "context" | "scheduler";

export function useChatShellState() {
  const { token } = useAuth();

  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<PanelId>("context");

  const { mutate: updateContext } = useMutation({
    mutationFn: ({ sessionId, docFilter }: { sessionId: string; docFilter: string | null }) => {
      if (!token) throw new Error("인증되지 않았습니다.");
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

  const handleNewChat = useCallback(() => {
    const newSessionId = crypto.randomUUID();
    setActiveSessionId(newSessionId);
    setSelectedDoc(null);
    if (token) {
      updateContext({ sessionId: newSessionId, docFilter: null });
    }
  }, [token, updateContext]);

  const handleSetSelectedDoc = useCallback(
    (docId: string | null) => {
      setSelectedDoc(docId);
      if (activeSessionId && token) {
        updateContext({ sessionId: activeSessionId, docFilter: docId });
      }
    },
    [activeSessionId, token, updateContext]
  );

  const handleSelectConversation = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
    setSelectedDoc(null);
  }, []);

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
