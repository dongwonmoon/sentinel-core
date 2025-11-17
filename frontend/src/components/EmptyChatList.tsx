/**
 * @file 사이드바에 표시할 채팅 세션이 없을 때 보여주는 '빈 상태(Empty State)' UI 컴포넌트입니다.
 * @description 사용자에게 아직 대화 기록이 없음을 알리고,
 * 새 대화를 시작하도록 유도하는 메시지를 표시합니다.
 */

export default function EmptyChatList() {
    return (
      // 'empty-state' 클래스를 통해 중앙 정렬 및 스타일링을 적용합니다.
      <div className="empty-state">
        {/* 시각적인 아이콘 */}
        <p>💬</p>
        {/* 사용자에게 현재 상태를 알려주는 메시지 */}
        <p className="muted">아직 대화 기록이 없습니다.</p>
        {/* 다음 행동을 유도하는 메시지 */}
        <p className="muted">새 대화를 시작하여 AI와 소통해보세요!</p>
      </div>
    );
  }
  