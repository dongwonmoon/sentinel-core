"""Agent의 상태 정의 및 관련 유틸리티 함수."""

from typing import TypedDict, List, Dict, Any, Literal, Optional


class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의하는 TypedDict입니다.
    그래프의 각 노드는 이 상태 객체의 일부를 읽고, 자신의 실행 결과를 이 객체에 기록합니다.
    이러한 중앙 집중식 상태 관리를 통해 그래프의 데이터 흐름을 명확하게 추적할 수 있습니다.
    """

    # --- 요청 입력 (그래프 시작 시 주입) ---
    question: str  # 사용자의 현재 질문
    top_k: int  # RAG 검색 결과에서 최종적으로 사용할 상위 K개 문서 수
    doc_ids_filter: Optional[List[str]]  # RAG 검색 범위를 특정 문서 ID로 제한할 때 사용
    chat_history: List[Dict[str, str]]  # 전체 대화 기록
    user_profile: Optional[str]  # 사용자 프로필 정보 (개인화된 답변 생성에 사용)
    user_id: Optional[str]  # 사용자 ID
    session_id: Optional[str]  # 현재 채팅 세션 ID

    # --- 컨텍스트 구축 노드(build_hybrid_context)의 출력 ---
    hybrid_context: str  # 단기/서사/장기 기억을 종합한 하이브리드 컨텍스트

    tool_choice: str
    tool_outputs: dict[str, Any]

    # --- 최종 출력 ---
    answer: str  # 에이전트가 생성한 최종 답변
