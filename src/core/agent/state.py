"""Agent의 상태 정의 및 관련 유틸리티 함수."""

from typing import TypedDict, List, Dict, Any, Literal, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage


class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의합니다. 그래프의 각 노드를 거치며 이 상태가 업데이트됩니다.
    """

    # 입력
    question: str
    permission_groups: List[str]
    top_k: int
    doc_ids_filter: Optional[List[str]]
    chat_history: List[Dict[str, str]]

    # 중간 상태
    chosen_llm: Literal["fast", "powerful"]
    tool_choice: str
    tool_outputs: Dict[str, Any]
    code_input: Optional[str] = None

    # 최종 출력
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
