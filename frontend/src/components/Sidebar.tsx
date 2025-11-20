/**
 * @file 애플리케이션의 좌측 사이드바 UI 컴포넌트입니다.
 * @description 이 컴포넌트는 다음과 같은 기능을 담당합니다:
 * - '새 대화' 시작 버튼 표시
 * - 기존 대화(채팅 세션) 목록 표시
 * - 사용자가 특정 대화를 선택하는 기능
 * - 사용자 정보, 프로필 수정 모달 열기, 로그아웃 버튼이 포함된 하단 푸터 표시
 */

import { useState } from "react";
import { ChatSession } from "../hooks/useChatSessionsList";
import ProfileModal from "./ProfileModal";
import { useAuth } from "../providers/AuthProvider";
import EmptyChatList from "./EmptyChatList";

/** Sidebar 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /**
   * 사이드바에 표시할 전체 대화 세션의 목록.
   * `useChatSessionsList` 훅으로부터 전달받습니다.
   */
  conversations: ChatSession[];
  /**
   * 현재 선택된 대화 세션의 ID.
   * 선택된 항목을 시각적으로 강조하는 데 사용됩니다.
   */
  selectedConversation: string | null;
  /**
   * 사용자가 특정 대화를 선택했을 때 호출될 콜백 함수입니다.
   * @param id 선택된 대화 세션의 ID
   */
  onSelectConversation: (id: string | null) => void;
  /**
   * 사용자가 '새 대화' 버튼을 클릭했을 때 호출될 콜백 함수입니다.
   */
  onNewChat: () => void;
};

export default function Sidebar({
    conversations,
    selectedConversation,
    onSelectConversation,
    onNewChat,
}: Props) {
  // `useAuth` 훅을 통해 현재 사용자 정보와 로그아웃 함수를 가져옵니다.
  const { user, signOut } = useAuth();
  // 프로필 모달의 열림/닫힘 상태를 관리합니다.
  const [showProfileModal, setShowProfileModal] = useState(false);  

  // 방어적 코딩: 인증 정보가 없으면 컴포넌트를 렌더링하지 않습니다.
  if (!user) return null;

  return (
    <>
      <aside className="sidebar">
        {/* 상단 영역: 새 대화 버튼 + 세션 목록 */}
        <div className="sidebar-top-content">
          <button className="primary full" onClick={onNewChat}>
            새 대화
          </button>

          {/* 대화 목록 */}
          <div className="sidebar-list">
            {/* 대화 목록이 비어있을 경우 '빈 상태' 컴포넌트를 렌더링합니다. */}
            {conversations.length === 0 ? (
              <EmptyChatList />
            ) : (
              // 대화 목록을 순회하며 각 대화를 버튼으로 렌더링합니다.
              conversations.map((item) => (
                <button
                  key={item.session_id}
                  className={
                    // 현재 선택된 대화는 'active' 클래스를 적용하여 시각적으로 강조합니다.
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
            {/* 프로필 모달을 여는 버튼 */}
            <button
              className="ghost gemini-icon-button"
              onClick={() => setShowProfileModal(true)}
              title="프로필"
            >
              👤
            </button>
            {/* 로그아웃 버튼 */}
            <button 
              className="ghost gemini-icon-button"
              onClick={signOut}
              title="로그아웃"
            >
              🚪
            </button>
          </div>
          {/* 현재 로그인된 사용자 정보 */}
          <div className="sidebar-user-info">
            <p className="sidebar-username">{user.username}</p>
            <small>Sentinel Core</small>
          </div>
        </div>
      </aside>

      {/* 프로필 모달 (showProfileModal 상태가 true일 때만 렌더링) */}
      {showProfileModal && (
        <ProfileModal onClose={() => setShowProfileModal(false)} />
      )}
    </>
  );
}
