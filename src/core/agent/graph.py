"""Agent의 LangGraph 그래프를 구성하고 컴파일합니다."""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import AgentNodes


def _decide_branch(state: AgentState) -> str:
    """라우터의 결정에 따라 그래프를 분기합니다."""
    return state.get("tool_choice", "None")


def build_graph(nodes: AgentNodes) -> StateGraph:
    """
    조건부 라우팅을 포함하는 LangGraph 워크플로우를 구성하고 컴파일합니다.
    """
    workflow = StateGraph(AgentState)

    # 노드 등록
    workflow.add_node("route_query", nodes.route_query)
    workflow.add_node("run_rag_tool", nodes.run_rag_tool)
    workflow.add_node("run_web_search_tool", nodes.run_web_search_tool)
    workflow.add_node("run_code_execution_tool", nodes.run_code_execution_tool)
    workflow.add_node("generate_final_answer", nodes.generate_final_answer)

    # 엣지 연결
    workflow.set_entry_point("route_query")
    workflow.add_conditional_edges(
        "route_query",
        _decide_branch,
        {
            "RAG": "run_rag_tool",
            "WebSearch": "run_web_search_tool",
            "CodeExecution": "run_code_execution_tool",
            "None": "generate_final_answer",
        },
    )
    workflow.add_edge("run_rag_tool", "generate_final_answer")
    workflow.add_edge("run_web_search_tool", "generate_final_answer")
    workflow.add_edge("run_code_execution_tool", "generate_final_answer")
    workflow.add_edge("generate_final_answer", END)

    return workflow.compile()
