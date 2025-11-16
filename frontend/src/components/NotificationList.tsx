import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";
import { Notification } from "../hooks/useNotifications";
import { notify } from "./NotificationHost";
import { useAuth } from "../providers/AuthProvider";
import Modal from "./Modal";

type Props = {
  notifications: Notification[];
  onClose: () => void;
};

export default function NotificationList({ notifications, onClose }: Props) {
  const { token } = useAuth();
  if (!token) return null;

  const queryClient = useQueryClient();

  // 1. useMutation으로 "읽음 처리" API (POST /notifications/{id}/read) 호출
  const { mutate, isPending } = useMutation({
    mutationFn: (notificationId: number) =>
      apiRequest(`/notifications/${notificationId}/read`, {
        method: "POST",
        token: token,
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

  const isEmpty = notifications.length === 0;

  return (
    <Modal onClose={onClose} maxHeight="60vh">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ marginBottom: 0 }}>알림</h2>
          <small className="muted">
            {isEmpty ? "새로운 알림이 없습니다." : `${notifications.length}개의 읽지 않은 알림`}
          </small>
        </div>
        <button type="button" className="ghost" onClick={onClose}>
          닫기
        </button>
      </div>

      <div
        className="doc-list"
        style={{
          flex: 1,
          maxHeight: "45vh",
          overflowY: "auto",
          paddingRight: "0.5rem",
          marginTop: "1rem",
        }}
      >
        {isEmpty ? (
          <p className="muted">나중에 다시 확인해 주세요.</p>
        ) : (
          notifications.map((notif) => (
            <div key={notif.notification_id} className="doc-item" style={{ alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontWeight: 600 }}>{notif.message}</p>
                <small className="muted">{formatRelativeTime(notif.created_at)}</small>
              </div>
              <button
                className="ghost"
                onClick={() => mutate(notif.notification_id)}
                disabled={isPending}
                title="읽음 처리"
              >
                완료
              </button>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
}

function formatRelativeTime(value: string) {
  const date = new Date(value);
  const now = Date.now();
  const diffMs = now - date.getTime();
  if (Number.isNaN(diffMs) || diffMs < 0) {
    return "방금";
  }
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return `${days}일 전`;
}
