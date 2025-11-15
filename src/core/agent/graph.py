# -*- coding: utf-8 -*-
"""
에이전트의 핵심 워크플로우를 LangGraph 상태 머신(State Machine)으로 구성하고 컴파일합니다.

이 파일의 `build_graph` 함수는 에이전트의 작동 방식을 시각적인 그래프 형태로 정의합니다.
- **상태 (State)**: `AgentState`는 그래프의 모든 노드가 공유하는 중앙 데이터 저장소입니다.
- **노드 (Node)**: 그래프의 각 단계(Step)로, 특정 작업을 수행합니다. (예: 질문 라우팅, RAG 실행)
- **엣지 (Edge)**: 노드 간의 연결선으로, 작업의 흐름을 정의합니다.
- **조건부 엣지 (Conditional Edge)**: 상태(State) 값에 따라 동적으로 다음에 실행할 노드를 결정하여,
  에이전트가 유연하게 상황에 맞는 도구를 선택할 수 있게 합니다.
"""

from langgraph.graph import END, StateGraph

from ..logger import get_logger
from .nodes import AgentNodes
from .state import AgentState

logger = get_logger(__name__)


def _decide_branch(state: AgentState) -> str:
    """
    [조건부 엣지 함수] 'route_query' 노드의 결정에 따라 다음에 실행할 노드를 선택합니다.

    `AgentState`의 `tool_choice` 값 (예: "RAG", "WebSearch")을 그대로 반환하여,
    `add_conditional_edges`에 명시된 매핑에 따라 그래프가 분기되도록 합니다.

    Args:
        state (AgentState): 현재 에이전트의 상태. `route_query` 노드 실행 후의 결과가 담겨 있습니다.

    Returns:
        str: 다음에 실행할 노드의 이름과 매핑되는 키 (예: "RAG", "WebSearch").
    """
    tool_choice = state.get("tool_choice", "None")
    logger.info(f"라우팅 결정: '{tool_choice}' 도구를 선택했습니다.")

    # 예기치 않은 tool_choice 값에 대한 안전장치. "None"으로 처리하여 바로 답변 생성으로 넘어갑니다.
    if tool_choice not in ["RAG", "WebSearch", "CodeExecution", "None"]:
        logger.warning(
            f"예상치 못한 도구 '{tool_choice}'가 선택되었습니다. 'None'으로 처리합니다."
        )
        return "None"
    return tool_choice


def _check_rag_failure(state: AgentState) -> str:
    """
    [조건부 엣지 함수] 'run_rag_tool' 노드 실행 후, RAG 검색 실패 여부를 확인하여 분기합니다.

    - RAG 검색 결과가 없어 `failed_tools` 상태에 'RAG'가 추가된 경우:
      'retry'를 반환하여 'route_query' 노드로 다시 돌아가 다른 도구(예: 웹 검색)를 시도하게 합니다.
    - RAG 검색에 성공한 경우:
      'continue'를 반환하여 'generate_final_answer' 노드로 진행합니다.

    Args:
        state (AgentState): `run_rag_tool` 노드 실행 후의 상태.

    Returns:
        str: 'retry' 또는 'continue', 분기할 엣지의 키.
    """
    if "RAG" in state.get("failed_tools", []):
        logger.warning(
            "RAG 도구 실행에 실패했습니다. 다른 도구를 시도하기 위해 재라우팅합니다."
        )
        return "retry"

    logger.info("RAG 도구 실행에 성공했습니다. 답변 생성을 계속합니다.")
    return "continue"


def build_graph(nodes: AgentNodes) -> StateGraph:
    """
    에이전트의 전체 워크플로우를 LangGraph로 구성하고 컴파일합니다.

    Args:
        nodes (AgentNodes): 각 노드의 실제 실행 로직을 담고 있는 객체.

    Returns:
        StateGraph: 컴파일되어 실행 가능한 LangGraph 객체.
    """
    logger.info("LangGraph 워크플로우 빌드를 시작합니다...")
    # AgentState를 상태 객체로 사용하는 StateGraph를 초기화합니다.
    workflow = StateGraph(AgentState)

    # --- 1. 노드(Node) 등록 ---
    # 각 노드의 이름과 해당 노드가 실행할 함수(AgentNodes의 메서드)를 매핑합니다.
    logger.debug(
        "그래프에 노드를 추가합니다: route_query, run_rag_tool, run_web_search_tool, run_code_execution_tool, generate_final_answer, output_guardrail"
    )
    workflow.add_node("route_query", nodes.route_query)
    workflow.add_node("run_rag_tool", nodes.run_rag_tool)
    workflow.add_node("run_web_search_tool", nodes.run_web_search_tool)
    workflow.add_node("run_code_execution_tool", nodes.run_code_execution_tool)
    workflow.add_node("generate_final_answer", nodes.generate_final_answer)
    workflow.add_node("output_guardrail", nodes.output_guardrail)

    # --- 2. 엣지(Edge) 연결 ---
    # 노드 간의 실행 흐름(데이터 흐름)을 정의합니다.

    # 그래프의 진입점(Entry Point)을 'route_query' 노드로 설정합니다.
    # 모든 요청은 이 노드에서 시작됩니다.
    workflow.set_entry_point("route_query")
    logger.debug("그래프 진입점을 'route_query'로 설정했습니다.")

    # 'route_query' 노드 이후의 조건부 분기 설정
    # `_decide_branch` 함수의 반환값에 따라 다음에 실행될 노드가 결정됩니다.
    workflow.add_conditional_edges(
        "route_query",  # 시작 노드
        _decide_branch,  # 분기 로직을 담은 함수
        {  # 분기 함수의 반환값과 다음 노드를 매핑하는 딕셔너리
            "RAG": "run_rag_tool",
            "WebSearch": "run_web_search_tool",
            "CodeExecution": "run_code_execution_tool",
            "None": "generate_final_answer",  # 도구가 필요 없으면 바로 답변 생성으로
        },
    )
    logger.debug("'route_query' 노드 이후의 조건부 엣지를 설정했습니다.")

    # 'run_rag_tool' 노드 이후의 조건부 분기 설정
    # `_check_rag_failure` 함수의 반환값에 따라 분기합니다.
    workflow.add_conditional_edges(
        "run_rag_tool",
        _check_rag_failure,
        {
            "continue": "generate_final_answer",  # 성공 시 답변 생성으로
            "retry": "route_query",  # 실패 시 다시 라우팅으로
        },
    )
    logger.debug("'run_rag_tool' 노드 이후의 조건부 엣지를 설정했습니다.")

    # 다른 도구 노드들은 실행 완료 후 항상 'generate_final_answer' 노드로 이동하는 일반 엣지를 추가합니다.
    workflow.add_edge("run_web_search_tool", "generate_final_answer")
    workflow.add_edge("run_code_execution_tool", "generate_final_answer")
    logger.debug(
        "WebSearch 및 CodeExecution 도구에서 'generate_final_answer'로의 엣지를 추가했습니다."
    )

    # 최종 답변 생성 후, 'output_guardrail' 노드를 거쳐 안전성을 검증합니다.
    workflow.add_edge("generate_final_answer", "output_guardrail")
    logger.debug(
        "'generate_final_answer'에서 'output_guardrail'로의 엣지를 추가했습니다."
    )

    # 가드레일 통과 후, 그래프 실행을 종료합니다. (END는 LangGraph의 특별한 노드 이름)
    workflow.add_edge("output_guardrail", END)
    logger.debug(
        "'output_guardrail'에서 그래프 종료(END)로의 엣지를 추가했습니다."
    )

    # --- 3. 그래프 컴파일 ---
    # 위에서 정의된 노드와 엣지 구성을 바탕으로 실행 가능한 객체를 생성하여 반환합니다.
    logger.info("LangGraph 워크플로우 컴파일을 시작합니다...")
    compiled_graph = workflow.compile()
    logger.info("LangGraph 워크플로우가 성공적으로 컴파일되었습니다.")
    return compiled_graph
