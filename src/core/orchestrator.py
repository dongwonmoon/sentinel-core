# -*- coding: utf-8 -*-
"""
AI 에이전트의 핵심 오케스트레이션 모듈.

`Orchestrator` 클래스는 LangGraph를 사용하여 RAG, 도구 사용 등
복잡한 AI 워크플로우를 관리하고 실행합니다.
"""
from typing import Any, AsyncIterator, Dict

from .agent.graph import build_graph
from .agent.nodes import AgentNodes
from .logger import get_logger
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)


class Orchestrator:
    """
    RAG, 도구 사용 등 에이전트 워크플로우를 조정하는 핵심 클래스.

    LangGraph 상태 머신을 사용하여 LLM, 도구, 벡터 저장소의 상호작용을 관리합니다.
    """

    def __init__(
        self,
        llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
    ):
        """Orchestrator 인스턴스를 초기화합니다.

        Args:
            llm (BaseLLM): 에이전트가 사용할 LLM.
            vector_store (BaseVectorStore): 문서 검색을 위한 벡터 저장소.
            reranker (BaseReranker): 검색 결과 재순위를 위한 리랭커.
        """
        logger.info("오케스트레이터(Orchestrator) 초기화를 시작합니다...")

        self.vector_store = vector_store
        self.reranker = reranker

        # TODO: 현재 비어있는 도구 리스트를 외부에서 주입받아 동적으로 설정해야 합니다.
        tools_dict = {tool.name: tool for tool in []}

        logger.info(f"사용 가능한 도구: {list(tools_dict.keys())}")
        logger.info(f"LLM: {llm.model_name} ({llm.provider})")
        logger.info(f"Vector Store: {vector_store.provider}")
        logger.info(f"Reranker: {reranker.provider}")

        # AgentNodes는 그래프의 각 노드에서 실행될 로직을 캡슐화합니다.
        # TODO: AgentNodes는 vector_store의 읽기 기능만 필요하므로, 읽기 전용 인터페이스를 제공하여 안정성을 높여야 합니다.
        logger.debug("AgentNodes를 초기화합니다...")
        nodes = AgentNodes(
            llm=llm,
            vector_store=self.vector_store,
            reranker=self.reranker,
            tools=tools_dict,
        )

        # 정의된 노드들을 바탕으로 실행 가능한 상태 그래프를 빌드합니다.
        logger.debug("LangGraph 워크플로우를 빌드하고 컴파일합니다...")
        self.graph_app = build_graph(nodes)
        logger.info("오케스트레이터 초기화가 성공적으로 완료되었습니다.")

    async def stream_response(
        self, inputs: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """입력에 대한 AI 에이전트의 응답을 스트리밍합니다.

        LangGraph 워크플로우를 실행하고, LLM 토큰 생성, 도구 사용 등
        중간 처리 과정을 이벤트 스트림으로 반환합니다.

        Args:
            inputs (Dict[str, Any]): 워크플로우 실행에 필요한 입력.
                                     (예: {'question': '...'})

        Yields:
            AsyncIterator[Dict[str, Any]]: 그래프 실행 중 발생하는 이벤트.
        """
        logger.info(
            "LangGraph 스트림을 시작합니다. 질문: '%s...'",
            inputs.get("question", "")[:80],
        )
        logger.debug("스트림 입력 데이터: %s", inputs)

        # astream_events를 통해 그래프 실행의 모든 중간 과정을 비동기적으로 스트리밍합니다.
        async for event in self.graph_app.astream_events(inputs, version="v1"):
            yield event

        logger.info("LangGraph 스트림이 종료되었습니다.")
