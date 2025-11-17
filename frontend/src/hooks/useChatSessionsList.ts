/**
 * @file 사용자의 모든 채팅 세션 목록을 가져오는 React Query 훅을 정의합니다.
 * @description 이 훅은 TanStack Query(`useQuery`)를 사용하여
 * `/chat/sessions` API 엔드포인트에서 데이터를 가져오고,
 * 해당 데이터를 캐싱하여 관리합니다.
 */

import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";

/**
 * 백엔드 `schemas.py`의 `ChatSession` 모델과 일치하는 타입입니다.
 * 사이드바에 표시될 개별 대화 항목의 데이터를 나타냅니다.
 */
export type ChatSession = {
  /** 대화 세션의 고유 ID */
  session_id: string;
  /**
   * 대화의 제목.
   * 백엔드에서 대화 내용의 첫 부분으로 자동 생성되거나 사용자가 직접 설정할 수 있습니다.
   */
  title: string;
  /** 세션이 마지막으로 업데이트된 시간 (ISO 8601 형식의 문자열) */
  last_updated: string;
};

/**
 * 사용자의 모든 채팅 세션 목록을 가져오는 React Query 훅입니다.
 * @param token 인증에 사용될 JWT 토큰
 * @returns TanStack Query의 `useQueryResult` 객체.
 *          `data` 필드에 `ChatSession[]`이 포함됩니다.
 */
export function useChatSessionsList(token: string) {
  return useQuery({
    // `queryKey`: 이 쿼리 데이터를 식별하는 고유한 키입니다.
    // React Query는 이 키를 사용하여 데이터를 캐싱하고, 다른 컴포넌트에서
    // 동일한 키로 `useQuery`를 호출하면 캐시된 데이터를 반환합니다.
    queryKey: ["chatSessions"], 
    
    // `queryFn`: 실제 데이터 페칭 로직을 수행하는 비동기 함수입니다.
    queryFn: async () => {
      // 브라우저 캐시를 우회하고 항상 최신 데이터를 가져오기 위해 타임스탬프를 쿼리 파라미터로 추가합니다.
      const timestamp = Date.now().toString();
      
      // 백엔드 응답(`ChatSessionListResponse`)에서 'sessions' 배열을 추출합니다.
      const data = await apiRequest<{ sessions: ChatSession[] }>(
        `/chat/sessions?t=${timestamp}`,
        {
          token,
          errorMessage: "대화 세션 목록을 불러오지 못했습니다.",
        },
      );
      return data.sessions;
    },
    
    // `enabled`: 이 쿼리가 자동으로 실행될지 여부를 결정하는 옵션입니다.
    // `!!token`은 `token`이 존재하고 비어있지 않은 문자열일 때만 `true`가 됩니다.
    // 이를 통해, 사용자가 아직 로그인하지 않아 토큰이 없는 상태에서
    // 불필요한 API 요청이 나가는 것을 방지합니다.
    enabled: !!token, 
  });
}
