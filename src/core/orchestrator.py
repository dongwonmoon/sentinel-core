"""
핵심 에이전트(Agent) 로직을 담당하는 모듈입니다.
LangGraph를 사용하여 RAG, 웹 검색, 코드 실행 등 다양한 도구를 조정합니다.
"""

from typing import List, Dict, Any, AsyncIterator

from .logger import get_logger
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.vector_stores.base import BaseVectorStore
from ..components.tools.base import BaseTool
from .agent.nodes import AgentNodes
from .agent.graph import build_graph


logger = get_logger(__name__)


class Agent:
    """
    LangGraph를 사용하여 RAG, 웹 검색 등을 조정하는 에이전트의 핵심 로직.
    """

    def __init__(
        self,
        fast_llm: BaseLLM,
        powerful_llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        tools: List[BaseTool],
    ):
        """
        Agent 인스턴스를 초기화합니다.

        Args:
            fast_llm: 빠른 LLM (라우팅, 간단한 답변용)
            powerful_llm: 강력한 LLM (복잡한 추론, 코드 생성용)
            vector_store: 벡터 저장소 인스턴스
            reranker: 리랭커 인스턴스
            tools: 사용 가능한 도구 리스트
        """
        # vector_store와 reranker를 self에 저장
        self.vector_store = vector_store
        self.reranker = reranker
        
        tools_dict = {tool.name: tool for tool in tools}
        logger.info(f"Agent 초기화 완료. 사용 가능 도구: {list(tools_dict.keys())}")
        logger.info(
            f"Fast LLM: {fast_llm.model_name}, Powerful LLM: {powerful_llm.model_name}"
        )

        # 1. 노드 실행 로직을 담는 클래스 인스턴스화
        nodes = AgentNodes(
            fast_llm=fast_llm,
            powerful_llm=powerful_llm,
            vector_store=self.vector_store,
            reranker=self.reranker,
            tools=tools_dict,
        )

        # 2. 그래프 빌드 및 컴파일
        self.graph_app = build_graph(nodes)

    async def stream_response(
        self, inputs: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        LangGraph의 astream_events를 사용하여 답변 생성 과정을 스트리밍합니다.
        """
        logger.debug(
            "LangGraph 스트림 시작 - 질문='%s', 권한=%s",
            inputs.get("question", "")[:80],
            inputs.get("permission_groups"),
        )
        async for event in self.graph_app.astream_events(inputs, version="v1"):
            yield event
