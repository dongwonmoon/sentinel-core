import { useState } from "react";
import { ChatSession } from "../hooks/useChatSessionsList";
import ProfileModal from "./ProfileModal";
import { useNotifications } from "../hooks/useNotifications";
import NotificationList from "./NotificationList";
import { useAuth } from "../providers/AuthProvider";

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
  const { user, signOut } = useAuth();
  if (!user) return null;

  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showNotificationModal, setShowNotificationModal] = useState(false);
  
  const { data: notifications } = useNotifications(user.token);
  const unreadCount = notifications?.length || 0;

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div>
            <p className="sidebar-username">{user.username}</p>
            <small>Sentinel Core</small>
          </div>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button
              className="ghost"
              onClick={() => setShowNotificationModal(true)}
              style={{ position: 'relative' }}
            >
              🔔              
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute', top: 0, right: 0, width: '10px', height: '10px',
                  background: '#f87171', borderRadius: '50%', border: '2px solid #1e1f30'
                }} />
              )}
            </button>
            <button
              className="ghost"
              onClick={() => setShowProfileModal(true)}
            >
              프로필
            </button>
            <button className="ghost" onClick={signOut}>
              로그아웃
            </button>
          </div>
        </div>

        <button className="primary full" onClick={onNewChat}>
          새 대화
        </button>

        <div className="sidebar-list">
          {conversations.length === 0 && (
            <p className="muted">대화 기록이 없습니다.</p>
          )}

          {conversations.map((item) => (
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
          ))}
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
