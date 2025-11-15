import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";

// 1. 백엔드 `notifications.py`의 응답 타입과 일치하는 타입
export type Notification = {
  notification_id: number;
  message: string;
  created_at: string; // (날짜/시간은 문자열로 받습니다)
};

export function useNotifications(token: string) {
  return useQuery({
    // 2. react-query가 이 데이터를 식별할 고유 키
    queryKey: ["notifications"],
    queryFn: async () => {
      return apiRequest<Notification[]>("/notifications", {
        token,
        errorMessage: "알림을 불러오지 못했습니다.",
      });
    },
    // 3. (중요) 이 훅이 활성화된 토큰이 있을 때만 실행
    enabled: !!token,
    // 4. (선택) 1분마다 새로운 알림이 있는지 백그라운드에서 자동 확인
    refetchInterval: 60 * 1000,
  });
}