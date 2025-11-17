/**
 * @file 채팅 메시지 입력창(Composer) UI 컴포넌트입니다.
 * @description 사용자가 텍스트를 입력하고, 메시지를 전송하거나,
 * 파일 업로드 모달을 열 수 있는 인터페이스를 제공합니다.
 */

import { useState } from "react";

type Props = {
  /**
   * 입력창의 비활성화 상태를 제어합니다.
   * AI가 응답을 생성하는 동안(loading) true로 설정됩니다.
   */
  disabled: boolean;
  /**
   * 사용자가 메시지를 전송할 때 호출될 콜백 함수입니다.
   * @param text 사용자가 입력한 텍스트 메시지
   */
  onSend: (text: string) => Promise<void>;
  /**
   * 파일 업로드 모달을 열기 위해 호출될 콜백 함수입니다.
   * '+' 버튼 클릭 시 실행됩니다.
   */
  onOpenUploadModal: () => void;
};

/**
 * 채팅 입력창. 텍스트 전송과 업로드 모달 열기(+ 버튼)를 담당한다.
 */
export default function Composer({ disabled, onSend, onOpenUploadModal }: Props) {
  // 사용자가 입력하는 텍스트를 관리하는 상태
  const [text, setText] = useState("");
  
  /**
   * 폼 제출(전송 버튼 클릭 또는 Enter 키) 시 호출되는 핸들러입니다.
   */
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); // 폼 기본 동작(새로고침) 방지
    if (!text.trim()) return; // 내용이 없는 메시지는 전송하지 않음

    // 메시지 전송 후 입력창을 즉시 비우기 위해 현재 텍스트를 복사합니다.
    const snapshot = text;
    setText("");
    
    // 상위 컴포넌트로부터 받은 onSend 함수를 호출하여 메시지를 전송합니다.
    await onSend(snapshot);
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-inner">
        {/* 메시지 입력 텍스트 영역 */}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="질문을 입력하세요..."
          rows={1}
          disabled={disabled}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />
        
        {/* 파일 업로드 모달을 여는 버튼 */}
        <button
          type="button"
          className="ghost gemini-icon-button"
          onClick={onOpenUploadModal}
          disabled={disabled}
          title="파일/코드 첨부 (이 세션에서만 사용)"
        >
          +
        </button>
        
        {/* 메시지 전송 버튼 */}
        <button 
          type="submit" 
          disabled={disabled || !text.trim()} // 로딩 중이거나 입력 내용이 없으면 비활성화
          className="gemini-icon-button"
          title="보내기"
        >
          ⬆️
        </button>
      </div>
    </form>
  );
}
