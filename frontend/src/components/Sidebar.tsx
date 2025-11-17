import { useState } from "react";
import { ChatSession } from "../hooks/useChatSessionsList";
import ProfileModal from "./ProfileModal";
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

  return (
    <>
      <aside className="sidebar">
        {/* 상단 영역: 새 대화 버튼 + 세션 목록 */}
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

        {/* 하단 영역: 사용자 정보 / 프로필 / 로그아웃 */}
        <div className="sidebar-footer">
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
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
    </>
  );
}
