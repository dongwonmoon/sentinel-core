import { Message } from "../hooks/useChatSession";

type Props = {
  toolCall: NonNullable<Message["toolCall"]>; // toolCall 객체 (null이 아님)
};

// (솔루션 3) DB에 저장된 도구 이름과 UI에 표시할 레이블 매핑
const TOOL_LABELS: Record<string, string> = {
  run_rag_tool: "사내 RAG 검색",
  run_web_search_tool: "웹 검색",
  run_code_execution_tool: "코드 실행",
  run_dynamic_tool: "외부 도구 호출", // (이름은 동적으로 받는 것이 더 좋을 수 있음)
};

export default function ToolCallWidget({ toolCall }: Props) {
  const label = TOOL_LABELS[toolCall.name] || toolCall.name.replace("run_", "");

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        fontStyle: "italic",
        color: "var(--color-text-muted)",
        background: "rgba(255, 255, 255, 0.03)",
        borderRadius: "12px",
        padding: "0.75rem 1rem",
      }}
    >
      {toolCall.status === "running" ? (
        <span className="spinner"></span> // (styles.css에 .spinner 정의 필요)
      ) : (
        <span style={{ color: "#10b981" }}>✔</span>
      )}
      <span>
        {label}
        {toolCall.status === "running" ? " 중..." : " 완료"}
      </span>
    </div>
  );
}