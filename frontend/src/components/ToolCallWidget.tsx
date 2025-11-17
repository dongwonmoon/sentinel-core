/**
 * @file AI 에이전트의 '도구 호출(Tool Call)' 상태를 시각적으로 표시하는 위젯 컴포넌트입니다.
 * @description 이 컴포넌트는 `Message` 객체에 `toolCall` 정보가 포함되어 있을 때
 * 일반 텍스트 메시지 대신 렌더링됩니다. 에이전트가 어떤 도구를 사용하고 있는지,
 * 그리고 그 도구가 현재 실행 중인지 또는 완료되었는지를 사용자에게 보여주어
 * 시스템의 투명성을 높입니다.
 */

import { Message } from "../hooks/useChatSession";

/** ToolCallWidget 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /**
   * `Message` 객체에서 추출된 도구 호출 정보.
   * `NonNullable`을 사용하여 이 prop은 null이나 undefined가 아님을 보장합니다.
   */
  toolCall: NonNullable<Message["toolCall"]>; // toolCall 객체 (null이 아님)
};

/**
 * 백엔드에서 사용하는 도구 이름(ID)과 프론트엔드 UI에 표시할
 * 사용자 친화적인 레이블을 매핑하는 객체입니다.
 */
const TOOL_LABELS: Record<string, string> = {
  run_rag_tool: "사내 RAG 검색",
  run_web_search_tool: "웹 검색",
  run_code_execution_tool: "코드 실행",
  run_dynamic_tool: "외부 도구 호출", // (이름은 동적으로 받는 것이 더 좋을 수 있음)
};

/**
 * LangGraph 도구 실행 중/완료 상태를 시각화한다.
 * 메시지 리스트에서 toolCall 객체가 있으면 이 위젯이 대신 렌더링된다.
 */
export default function ToolCallWidget({ toolCall }: Props) {
  // `TOOL_LABELS` 맵을 사용하여 도구 이름에 맞는 레이블을 찾습니다.
  // 만약 맵에 없는 새로운 도구 이름이 들어오면, 'run_' 접두사를 제거하여 기본 레이블로 사용합니다.
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
      {/* 도구의 상태(`status`)에 따라 다른 아이콘을 표시합니다. */}
      {toolCall.status === "running" ? (
        // 'running' 상태일 경우, CSS로 애니메이션되는 스피너를 표시합니다.
        <span className="spinner"></span> // (styles.css에 .spinner 정의 필요)
      ) : (
        // 'complete' 상태일 경우, 성공을 의미하는 체크마크 아이콘을 표시합니다.
        <span style={{ color: "#10b981" }}>✔</span>
      )}
      {/* 도구의 레이블과 현재 상태 텍스트를 조합하여 표시합니다. */}
      <span>
        {label}
        {toolCall.status === "running" ? " 중..." : " 완료"}
      </span>
    </div>
  );
}
