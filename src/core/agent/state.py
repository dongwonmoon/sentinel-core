"""Agent의 상태 정의 및 관련 유틸리티 함수."""

from typing import TypedDict, List, Dict, Any, Literal, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.utils.pydantic import PydanticBaseModel


class DynamicTool(PydanticBaseModel):
    """
    데이터베이스에 등록된 '동적 도구'의 정보를 담는 Pydantic 모델입니다.
    이 모델은 DB에서 조회한 도구 정보를 파싱하고 유효성을 검증하는 데 사용됩니다.
    """

    name: str
    description: str
    api_endpoint_url: str
    json_schema: Dict[str, Any]
    permission_groups: List[str]

    def to_tool_string(self) -> str:
        """
        LLM이 도구의 사용법을 이해할 수 있는 형식의 문자열로 변환합니다.
        이 문자열은 라우터 프롬프트에 포함되어, LLM이 어떤 도구를 사용할지 결정하는 데 사용됩니다.
        """
        return f"- {self.name}: {self.description}, args_schema: {self.json_schema}"


class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의하는 TypedDict입니다.
    그래프의 각 노드는 이 상태 객체의 일부를 읽고, 자신의 실행 결과를 이 객체에 기록합니다.
    이러한 중앙 집중식 상태 관리를 통해 그래프의 데이터 흐름을 명확하게 추적할 수 있습니다.
    """

    # --- 요청 입력 (그래프 시작 시 주입) ---
    question: str  # 사용자의 현재 질문
    permission_groups: List[
        str
    ]  # 사용자의 권한 그룹 (RAG, 동적 도구 접근 제어에 사용)
    top_k: int  # RAG 검색 결과에서 최종적으로 사용할 상위 K개 문서 수
    doc_ids_filter: Optional[
        List[str]
    ]  # RAG 검색 범위를 특정 문서 ID로 제한할 때 사용
    chat_history: List[Dict[str, str]]  # 전체 대화 기록
    user_profile: Optional[
        str
    ]  # 사용자 프로필 정보 (개인화된 답변 생성에 사용)
    user_id: Optional[str]  # 사용자 ID
    session_id: Optional[str]  # 현재 채팅 세션 ID

    # --- 컨텍스트 구축 노드(build_hybrid_context)의 출력 ---
    hybrid_context: str  # 단기/서사/장기 기억을 종합한 하이브리드 컨텍스트
    available_dynamic_tools: List[
        DynamicTool
    ]  # 현재 사용자가 접근 가능한 동적 도구 목록

    # --- 라우터 노드(route_query)의 출력 ---
    chosen_llm: Literal["fast", "powerful"]  # 최종 답변 생성에 사용할 LLM 종류
    tool_choice: str  # 선택된 도구 이름 (예: "RAG", "WebSearch", "None")
    dynamic_tool_to_call: Optional[DynamicTool]  # 선택된 동적 도구의 상세 정보
    dynamic_tool_input: Optional[Dict[str, Any]]  # 동적 도구에 전달할 인자

    # --- 도구 실행 노드들의 출력 ---
    tool_outputs: Dict[str, Any]  # 각 도구의 실행 결과를 저장하는 딕셔너리
    code_input: Optional[str]  # CodeExecution 도구가 생성한 코드
    failed_tools: Optional[
        List[str]
    ]  # 실행에 실패한 도구 목록 (재라우팅 시 참고)

    # --- 최종 출력 ---
    answer: str  # 에이전트가 생성한 최종 답변


def convert_history_dicts_to_messages(
    history_dicts: List[Dict[str, str]],
) -> List[BaseMessage]:
    """채팅 기록(딕셔너리 리스트)을 LangChain 메시지 객체 리스트로 변환합니다."""
    messages = []
    for msg in history_dicts:
        # 'role' 값에 따라 적절한 LangChain 메시지 타입(HumanMessage, AIMessage)으로 매핑합니다.
        # 이는 LangChain의 LLM 및 프롬프트 템플릿과 호환성을 맞추기 위함입니다.
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content", "")))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg.get("content", "")))
    return messages
