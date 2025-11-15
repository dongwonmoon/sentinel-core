export default function EmptyChatList() {
  return (
    <div className="empty-state">
      <p>💬</p>
      <p className="muted">아직 대화 기록이 없습니다.</p>
      <p className="muted">새 대화를 시작하여 AI와 소통해보세요!</p>
    </div>
  );
}