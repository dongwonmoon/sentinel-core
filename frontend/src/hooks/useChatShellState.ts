import { useCallback, useState } from "react";

export type PanelId = "context" | "scheduler";

export function useChatShellState() {
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<PanelId>("context");

  const handleNewChat = useCallback(() => {
    setActiveSessionId(crypto.randomUUID());
  }, []);

  const handleSelectConversation = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
  }, []);

  return {
    selectedDoc,
    setSelectedDoc,
    activeSessionId,
    selectConversation: handleSelectConversation,
    activePanel,
    setActivePanel,
    handleNewChat,
  };
}
