import { useState, useRef } from "react";

type Props = {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
  onAttachFile: (file: File) => Promise<void>;
};

export default function Composer({ disabled, onSend }: Props) {
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
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="질문을 입력하세요... (📎 파일 첨부)"
        rows={3}
        disabled={disabled}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {/* 파일 첨부 버튼 */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          style={{ display: "none" }}
          // (accept 속성 추가 가능)
        />
        <button
          type="button"
          className="ghost" // 스타일 변경
          onClick={handleAttachClick}
          disabled={disabled}
          title="파일 첨부 (이 세션에서만 사용)"
          style={{ padding: "0.55rem", borderRadius: "12px" }}
        >
          📎
        </button>
        
        {/* 기존 전송 버튼 */}
        <button type="submit" disabled={disabled || !text.trim()}>
          보내기
        </button>
      </div>
    </form>
  );
}
