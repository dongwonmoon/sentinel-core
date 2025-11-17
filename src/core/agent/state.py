"""Agent의 상태 정의 및 관련 유틸리티 함수."""

from typing import TypedDict, List, Dict, Any, Literal, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.utils.pydantic import PydanticBaseModel


class DynamicTool(PydanticBaseModel):
    name: str
    description: str
    api_endpoint_url: str
    json_schema: Dict[str, Any]
    permission_groups: List[str]

    # LangChain 에이전트가 이 객체를 도구처럼 사용할 수 있게 함
    def to_tool_string(self) -> str:
        return f"- {self.name}: {self.description}, args_schema: {self.json_schema}"


class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의합니다. 그래프의 각 노드를 거치며 이 상태가 업데이트됩니다.
    """

    # --- 요청 입력 ---
    question: str
    permission_groups: List[str]
    top_k: int
    doc_ids_filter: Optional[List[str]]
    chat_history: List[Dict[str, str]]
    user_profile: Optional[str] = None
    user_id: Optional[str]
    session_id: Optional[str]
    # 하이브리드 컨텍스트 / 동적 도구 목록은 build_hybrid_context 노드가 채운다.
    hybrid_context: str
    available_dynamic_tools: List[DynamicTool]
    # 'route_query'가 선택한 동적 도구 정보
    dynamic_tool_to_call: Optional[DynamicTool] = None
    # 'route_query'가 LLM을 통해 생성한, 동적 도구에 전달할 인자(JSON)
    dynamic_tool_input: Optional[Dict[str, Any]] = None

    # --- 중간 상태 ---
    chosen_llm: Literal["fast", "powerful"]
    tool_choice: str
    tool_outputs: Dict[str, Any]
    code_input: Optional[str] = None
    failed_tools: Optional[List[str]] = None

    # --- 최종 출력 ---
    answer: str


def convert_history_dicts_to_messages(
    history_dicts: List[Dict[str, str]],
) -> List[BaseMessage]:
    """채팅 기록(딕셔너리 리스트)을 LangChain 메시지 객체 리스트로 변환합니다."""
    messages = []
    for msg in history_dicts:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content", "")))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg.get("content", "")))
    return messages
