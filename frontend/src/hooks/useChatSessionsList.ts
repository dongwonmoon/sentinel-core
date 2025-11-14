import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";

// 1. 백엔드 `schemas.py`의 ChatSession 모델과 일치하는 타입 정의
export type ChatSession = {
  session_id: string;
  title: string;
  last_updated: string; // (날짜/시간은 문자열로 받습니다)
};

export function useChatSessionsList(token: string) {
  return useQuery({
    // 2. react-query가 이 데이터를 식별할 고유 키
    queryKey: ["chatSessions"], 
    queryFn: async () => {
      const timestamp = Date.now().toString();
      // 3. 백엔드 응답(ChatSessionListResponse)에서 'sessions' 배열을 추출
      const data = await apiRequest<{ sessions: ChatSession[] }>(
        `/chat/sessions?t=${timestamp}`,
        {
          token,
          errorMessage: "대화 세션 목록을 불러오지 못했습니다.",
        },
      );
      return data.sessions;
    },
    // 4. (중요) 이 훅이 활성화된 토큰이 있을 때만 실행되도록 설정
    enabled: !!token, 
  });
}
