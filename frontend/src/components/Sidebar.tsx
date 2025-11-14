import { ChatSession } from "../hooks/useChatSessionsList";

type Props = {
  username: string;
  conversations: ChatSession[];
  selectedConversation: string | null;
  onSelectConversation: (id: string | null) => void;
  onSignOut: () => void;
  onNewChat: () => void;
};

export default function Sidebar({
  username,
  conversations,
  selectedConversation,
  onSelectConversation,
  onSignOut,
  onNewChat
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div>
          <p className="sidebar-username">{username}</p>
          <small>Sentinel Core</small>
        </div>
        <button className="ghost" onClick={onSignOut}>
          로그아웃
        </button>
      </div>
      <button className="primary full" onClick={onNewChat}>새 대화</button>
      <div className="sidebar-list">
        {conversations.length === 0 && <p className="muted">대화 기록이 없습니다.</p>}
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
  );
}
