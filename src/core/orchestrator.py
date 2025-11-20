# -*- coding: utf-8 -*-
"""
RAG 파이프라인과 에이전트 로직을 총괄하는 오케스트레이터 모듈입니다.

복잡한 AI 시스템은 LLM, 벡터 DB, 외부 API(검색, 코드 실행 등)와 같은 여러 컴포넌트의
상호작용으로 이루어집니다. 이 모듈의 `Orchestrator` 클래스는 이러한 컴포넌트들을
하나의 일관된 워크플로우로 엮어, 시스템의 복잡성을 관리하고 제어하는 중앙 조정자 역할을 합니다.

LangGraph를 기반으로 상태 머신(State Machine)을 구축하여, 사용자의 질문에 따라
RAG(검색 증강 생성), 웹 검색, 코드 실행 등 적절한 도구를 동적으로 선택하고 실행하는
지능적인 에이전트 로직을 구현합니다.
"""

from typing import Any, AsyncIterator, Dict, List

from .agent.graph import build_graph
from .agent.nodes import AgentNodes
from .logger import get_logger
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.tools.base import BaseTool
from ..components.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)


class Orchestrator:
    """
    LangGraph를 사용하여 RAG, 웹 검색, 코드 실행 등 다양한 도구를 조정하는
    애플리케이션의 핵심 오케스트레이터입니다.
    """

    def __init__(
        self,
        llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        # tools: List[BaseTool],
    ):
        """
        Orchestrator 인스턴스를 초기화합니다.

        이 과정에서 의존성 주입(Dependency Injection)을 통해 필요한 모든 컴포넌트
        (LLM, 벡터 저장소, 리랭커, 도구 등)를 전달받고, 이들을 사용하여
        LangGraph 기반의 워크플로우를 구성합니다.

        Args:
            fast_llm (BaseLLM): 빠른 응답이 필요한 작업(예: 라우팅, 간단한 답변)에 사용될 LLM.
            powerful_llm (BaseLLM): 복잡한 추론이나 코드 생성이 필요할 때 사용될 고성능 LLM.
            vector_store (BaseVectorStore): 문서 검색을 위한 벡터 저장소 인스턴스.
            reranker (BaseReranker): 검색된 문서의 순위를 재조정하여 정확도를 높이는 리랭커 인스턴스.
            tools (List[BaseTool]): 에이전트가 사용할 수 있는 도구(예: DuckDuckGo 검색, 코드 실행기)의 리스트.
        """
        logger.info("오케스트레이터(Orchestrator) 초기화를 시작합니다...")

        # 주입된 컴포넌트들을 인스턴스 변수로 저장합니다.
        self.vector_store = vector_store
        self.reranker = reranker

        # 도구 리스트를 이름-객체 매핑 형태의 딕셔너리로 변환하여, 이름으로 쉽게 도구를 찾아 사용할 수 있게 합니다.
        tools_dict = {tool.name: tool for tool in []}

        logger.info(f"사용 가능한 도구: {list(tools_dict.keys())}")
        logger.info(f"LLM: {llm.model_name} ({llm.provider})")
        logger.info(f"Vector Store: {vector_store.provider}")
        logger.info(f"Reranker: {reranker.provider}")

        # 1. LangGraph의 각 노드(Node)에서 실행될 실제 로직을 담고 있는 `AgentNodes` 클래스를 인스턴스화합니다.
        #    이 클래스에 모든 핵심 컴포넌트를 전달하여, 각 노드가 필요로 하는 기능에 접근할 수 있도록 합니다.

        # 인터페이스 오염: vector_store
        # Agent는 오직 "검색"만 필요한데, 쓰기/삭제 권한까지 가진 객체를 넘겨받음.
        logger.debug("AgentNodes를 초기화합니다...")
        nodes = AgentNodes(
            llm=llm,
            vector_store=self.vector_store,
            reranker=self.reranker,
            tools=tools_dict,
        )

        # 2. `build_graph` 함수를 호출하여 `AgentNodes`를 기반으로 LangGraph 워크플로우를 구성하고 컴파일합니다.
        #    컴파일된 그래프는 `self.graph_app`에 저장되어 실제 요청 처리 시 사용됩니다.
        logger.debug("LangGraph 워크플로우를 빌드하고 컴파일합니다...")
        self.graph_app = build_graph(nodes)
        logger.info("오케스트레이터 초기화가 성공적으로 완료되었습니다.")

    async def stream_response(
        self, inputs: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        입력(inputs)을 받아 LangGraph 워크플로우를 실행하고,
        그 처리 과정에서 발생하는 모든 이벤트를 비동기적으로 스트리밍합니다.

        `astream_events`는 LangGraph의 핵심 기능으로, 그래프의 각 노드 실행,
        LLM 토큰 생성 등 모든 중간 과정을 이벤트 형태로 반환해 줍니다.
        이를 통해 클라이언트는 챗봇의 생각 과정(tool-use)이나 실시간 답변 생성을
        사용자에게 시각적으로 보여줄 수 있습니다.

        Args:
            inputs (Dict[str, Any]): 그래프 실행에 필요한 초기 입력 데이터.
                                     주요 키: `question` (사용자 질문),
                                     `session_id` (채팅 세션 ID),
                                     `user_id` (사용자 ID),
                                     `permission_groups` (사용자 권한 그룹).

        Yields:
            AsyncIterator[Dict[str, Any]]: LangGraph 실행 과정에서 발생하는 이벤트 딕셔너리.
                                           각 이벤트는 `event`, `name`, `data` 등의 키를 포함하며,
                                           예를 들어 'on_chat_model_stream' 이벤트는
                                           LLM이 생성하는 토큰(`chunk`)을 담고 있습니다.
        """
        logger.info(
            "LangGraph 스트림을 시작합니다. 질문: '%s...'",
            inputs.get("question", "")[:80],
        )
        logger.debug("스트림 입력 데이터: %s", inputs)

        # `self.graph_app.astream_events`를 비동기적으로 순회하며
        # 발생하는 각 이벤트를 그대로 클라이언트에게 전달(yield)합니다.
        async for event in self.graph_app.astream_events(inputs, version="v1"):
            yield event

        logger.info("LangGraph 스트림이 종료되었습니다.")
