import { useState } from "react";

type Props = {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
  onOpenUploadModal: () => void;
};

export default function Composer({ disabled, onSend, onOpenUploadModal }: Props) {
  const [text, setText] = useState("");
  
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    const snapshot = text;
    setText("");
    await onSend(snapshot);
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-inner">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="질문을 입력하세요... (+ 파일 첨부)" // ⬅️ 플레이스홀더 텍스트 변경
          rows={1}
          disabled={disabled}
        />
        {/* ⬇️ input type="file" 제거 */}
        
        {/* ⬇️ '📎' 버튼을 '+' 버튼으로 변경하고, onClick 핸들러 교체 */}
        <button
          type="button"
          className="ghost gemini-icon-button"
          onClick={onOpenUploadModal} // ⬅️ 모달 열기 함수 호출
          disabled={disabled}
          title="파일/코드 첨부 (이 세션에서만 사용)"
        >
          +
        </button>
        
        <button 
          type="submit" 
          disabled={disabled || !text.trim()}
          className="gemini-icon-button"
          title="보내기"
        >
          ⬆️
        </button>
      </div>
    </form>
  );
}