import { useState, useRef } from "react";

type Props = {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
  onAttachFile: (file: File) => Promise<void>;
};

export default function Composer({ disabled, onSend, onAttachFile }: Props) {
  const [text, setText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    const snapshot = text;
    setText("");
    await onSend(snapshot);
  }

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onAttachFile(file);
    }
    // 동일한 파일 재업로드를 위해 input 값 초기화
    e.target.value = ""; 
  };

  return (
    // ⬇️ 1. <form>이 최상위 래퍼(.composer)가 됩니다.
    <form className="composer" onSubmit={handleSubmit}>
      {/* ⬇️ 2. 스타일링을 위한 내부 래퍼(.composer-inner)를 추가합니다. */}
      <div className="composer-inner">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="질문을 입력하세요... (📎 파일 첨부)"
          rows={1} // ⬅️ 3. 기본 rows를 1로 줄입니다.
          disabled={disabled}
        />
        {/* ⬇️ 4. 버튼들을 텍스트 영역 *안*으로 이동시킵니다. */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          style={{ display: "none" }}
        />
        <button
          type="button"
          className="ghost gemini-icon-button"
          onClick={handleAttachClick}
          disabled={disabled}
          title="파일 첨부 (이 세션에서만 사용)"
        >
          📎
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
