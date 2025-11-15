import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";
import { Notification } from "../hooks/useNotifications";
import { notify } from "./NotificationHost";

type Props = {
  token: string;
  notifications: Notification[];
  onClose: () => void;
};

export default function NotificationList({ token, notifications, onClose }: Props) {
  const queryClient = useQueryClient();

  // 1. useMutation으로 "읽음 처리" API (POST /notifications/{id}/read) 호출
  const { mutate, isPending } = useMutation({
    mutationFn: (notificationId: number) =>
      apiRequest(`/notifications/${notificationId}/read`, {
        method: "POST",
        token,
        errorMessage: "알림 처리에 실패했습니다.",
      }),
    onSuccess: () => {
      // 2. 성공 시 "notifications" 쿼리 캐시를 갱신하여 UI에서 즉시 사라지게 함
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) => {
      notify(err.message);
    },
  });

  return (
    // P1.3에서 만든 ProfileModal과 동일한 스타일 재사용
    <div className="auth-wrapper" style={{ zIndex: 10 }} onClick={onClose}>
      <div
        className="auth-card" //
        style={{ width: "min(500px, 90vw)", maxHeight: "70vh", display: "flex", flexDirection: "column" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2>알림</h2>
          <button type="button" className="ghost" onClick={onClose}>
            닫기
          </button>
        </div>

        {/* [신규] 👈 알림 목록 (doc-list 스타일 재사용) */}
        <div className="doc-list" style={{ flex: 1, maxHeight: "50vh", overflowY: "auto", paddingRight: '0.5rem' }}>
          {notifications.length === 0 ? (
            <p className="muted">새로운 알림이 없습니다.</p>
          ) : (
            notifications.map((notif) => (
              // doc-item 스타일 재사용
              <div key={notif.notification_id} className="doc-item">
                <p style={{ flex: 1, margin: 0, fontSize: '0.9rem' }}>{notif.message}</p>
                <button
                  className="ghost"
                  onClick={() => mutate(notif.notification_id)}
                  disabled={isPending}
                  title="읽음 처리"
                >
                  X
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}