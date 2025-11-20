from langgraph.graph import END, StateGraph
from ..logger import get_logger
from .nodes import AgentNodes
from .state import AgentState

logger = get_logger(__name__)


def build_graph(nodes: AgentNodes) -> StateGraph:
    # 1. 상태 그래프 초기화
    workflow = StateGraph(AgentState)

    # 2. 핵심 노드 등록 (불필요한 노드 제거)
    # - 컨텍스트 구축: 대화 기록 등을 가져옵니다.
    workflow.add_node("build_hybrid_context", nodes.build_hybrid_context)
    # - RAG 검색: 세션에 첨부된 파일이 있다면 무조건 검색을 시도합니다.
    workflow.add_node("run_rag_tool", nodes.run_rag_tool)
    # - 답변 생성: 검색 결과와 컨텍스트를 바탕으로 최종 답변을 생성합니다.
    workflow.add_node("generate_final_answer", nodes.generate_final_answer)

    # 3. 엣지 연결 (일직선 구조)
    workflow.set_entry_point("build_hybrid_context")

    # 컨텍스트 구축 -> RAG 실행
    workflow.add_edge("build_hybrid_context", "run_rag_tool")

    # RAG 실행 -> 답변 생성 (검색 결과가 없어도 답변 생성 단계로 넘어가서 처리)
    workflow.add_edge("run_rag_tool", "generate_final_answer")

    # 답변 생성 -> 종료
    workflow.add_edge("generate_final_answer", END)

    # 4. 컴파일
    return workflow.compile()
