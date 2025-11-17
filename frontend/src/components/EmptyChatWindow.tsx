/**
 * @file 활성화된 채팅 세션이 없을 때 메인 채팅창에 보여주는 '빈 상태(Empty State)' UI 컴포넌트입니다.
 * @description 사용자에게 새 대화를 시작하거나 기존 대화를 선택하도록 유도하는
 * 환영 메시지를 표시합니다.
 */

export default function EmptyChatWindow() {
    return (
      // 'empty-state' 클래스를 통해 중앙 정렬 및 스타일링을 적용합니다.
      <div className="empty-state">
        {/* 시각적인 아이콘 */}
        <p>✨</p>
        {/* 사용자에게 행동을 유도하는 메인 메시지 */}
        <p className="muted">무엇이든 물어보세요!</p>
        {/* 추가적인 안내 메시지 */}
        <p className="muted">궁금한 점을 입력하고 대화를 시작해보세요.</p>
      </div>
    );
  }
  