from langgraph.graph import END, StateGraph

from ..logger import get_logger
from .nodes import AgentNodes
from .state import AgentState

logger = get_logger(__name__)


def build_graph(nodes: AgentNodes) -> StateGraph:
    """에이전트의 상태 머신 그래프(Stateful Graph)를 빌드하고 컴파일합니다.

    이 그래프는 다음과 같은 간단한 순차적 워크플로우를 정의합니다:
    1. `build_hybrid_context`: 대화 기록 등 컨텍스트를 구성합니다.
    2. `run_rag_tool`: RAG(검색 증강 생성) 검색을 실행합니다.
    3. `generate_final_answer`: 검색 결과와 컨텍스트를 바탕으로 최종 답변을 생성합니다.

    Args:
        nodes (AgentNodes): 그래프의 각 노드에서 실행될 로직을 담은 객체입니다.

    Returns:
        StateGraph: 컴파일된 LangGraph 객체를 반환합니다.
    """
    workflow = StateGraph(AgentState)

    # 1. 그래프 노드 정의
    workflow.add_node("build_hybrid_context", nodes.build_hybrid_context)
    workflow.add_node("run_rag_tool", nodes.run_rag_tool)
    workflow.add_node("generate_final_answer", nodes.generate_final_answer)

    # 2. 그래프 엣지(흐름) 연결
    workflow.set_entry_point("build_hybrid_context")
    workflow.add_edge("build_hybrid_context", "run_rag_tool")
    workflow.add_edge("run_rag_tool", "generate_final_answer")
    workflow.add_edge("generate_final_answer", END)

    # 3. 그래프 컴파일
    return workflow.compile()
