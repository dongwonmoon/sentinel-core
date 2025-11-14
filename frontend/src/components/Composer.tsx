import { useState } from "react";

type Props = {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
};

export default function Composer({ disabled, onSend }: Props) {
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
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="질문을 입력하세요..."
        rows={3}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled || !text.trim()}>
        보내기
      </button>
    </form>
  );
}
