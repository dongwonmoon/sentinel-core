type Props = {
  username: string;
  conversations: { id: string; title: string }[];
  selectedConversation: string | null;
  onSelectConversation: (id: string | null) => void;
  onSignOut: () => void;
};

export default function Sidebar({
  username,
  conversations,
  selectedConversation,
  onSelectConversation,
  onSignOut,
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
      <button className="primary full">새 대화</button>
      <div className="sidebar-list">
        {conversations.length === 0 && <p className="muted">대화 기록이 없습니다.</p>}
        {conversations.map((item) => (
          <button
            key={item.id}
            className={item.id === selectedConversation ? "list-item active" : "list-item"}
            onClick={() => onSelectConversation(item.id)}
          >
            {item.title}
          </button>
        ))}
      </div>
    </aside>
  );
}
