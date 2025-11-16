import { useState } from "react";
import { ChatSession } from "../hooks/useChatSessionsList";
import ProfileModal from "./ProfileModal";
import { useNotifications } from "../hooks/useNotifications";
import NotificationList from "./NotificationList";
import { useAuth } from "../providers/AuthProvider";
import EmptyChatList from "./EmptyChatList";

type Props = {
  conversations: ChatSession[];
  selectedConversation: string | null;
  onSelectConversation: (id: string | null) => void;
  onNewChat: () => void;
};

export default function Sidebar({
  conversations,
  selectedConversation,
  onSelectConversation,
  onNewChat,
}: Props) {
  const { user, token, signOut } = useAuth();
  if (!user || !token) return null;

  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showNotificationModal, setShowNotificationModal] = useState(false);
  
  const { data: notifications } = useNotifications(token);
  const unreadCount = notifications?.length || 0;

  return (
    <>
      <aside className="sidebar">
        {/* ⬇️ 1. 새 대화 버튼과 대화 목록을 상단 컨테이너로 묶습니다. */}
        <div className="sidebar-top-content">
          <button className="primary full" onClick={onNewChat}>
            새 대화
          </button>

          <div className="sidebar-list">
            {conversations.length === 0 ? (
              <EmptyChatList />
            ) : (
              conversations.map((item) => (
                <button
                  key={item.session_id}
                  className={
                    item.session_id === selectedConversation
                      ? "list-item active"
                      : "list-item"
                  }
                  onClick={() => onSelectConversation(item.session_id)}
                >
                  {item.title}
                </button>
              ))
            )}
          </div>
        </div>

        {/* ⬇️ 2. 기존 헤더 내용을 하단 푸터 컨테이너(.sidebar-footer)로 이동시킵니다. */}
        <div className="sidebar-footer">
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button
              className="ghost gemini-icon-button" // ⬅️ Gemini 스타일 아이콘 버튼 클래스 적용
              onClick={() => setShowNotificationModal(true)}
              style={{ position: 'relative' }}
              title="알림"
            >
              🔔              
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute', top: 0, right: 0, width: '10px', height: '10px',
                  background: '#f87171', borderRadius: '50%', border: '2px solid var(--color-app-bg)'
                }} />
              )}
            </button>
            <button
              className="ghost gemini-icon-button" // ⬅️ Gemini 스타일 아이콘 버튼 클래스 적용
              onClick={() => setShowProfileModal(true)}
              title="프로필"
            >
              👤
            </button>
            <button 
              className="ghost gemini-icon-button" // ⬅️ Gemini 스타일 아이콘 버튼 클래스 적용
              onClick={signOut}
              title="로그아웃"
            >
              🚪
            </button>
          </div>
          <div className="sidebar-user-info">
            <p className="sidebar-username">{user.username}</p>
            <small>Sentinel Core</small>
          </div>
        </div>
      </aside>

      {showProfileModal && (
        <ProfileModal onClose={() => setShowProfileModal(false)} />
      )}
      
      {showNotificationModal && (
        <NotificationList
          notifications={notifications || []}
          onClose={() => setShowNotificationModal(false)}
        />
      )}
    </>
  );
}
