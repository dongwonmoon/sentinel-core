import asyncio
from typing import Any, Dict

from langchain_core.messages import HumanMessage

from ...components.llms.base import BaseLLM
from ...components.rerankers.base import BaseReranker
from ...components.tools.base import BaseTool
from ...components.vector_stores.base import BaseVectorStore
from .. import prompts
from ..logger import get_logger
from .state import AgentState

logger = get_logger(__name__)


class AgentNodes:
    """LangGraph의 각 노드에서 실행될 실제 로직을 정의하는 클래스."""

    def __init__(
        self,
        llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        tools: Dict[str, BaseTool],
    ):
        """AgentNodes 인스턴스를 초기화합니다.

        Args:
            llm (BaseLLM): 사용할 LLM.
            vector_store (BaseVectorStore): 사용할 벡터 저장소.
            reranker (BaseReranker): 사용할 리랭커.
            tools (Dict[str, BaseTool]): 사용 가능한 도구 딕셔너리.
        """
        self.llm = llm
        self.vector_store = vector_store
        self.reranker = reranker
        self.tools = tools

    async def build_hybrid_context(self, state: AgentState) -> Dict[str, Any]:
        """최근 대화 기록을 바탕으로 간단한 컨텍스트를 구축합니다."""
        logger.debug("--- [Node: build_hybrid_context] ---")

        # TODO: 컨텍스트에 포함할 대화 개수를 설정 가능하도록 변경 (현재 10개로 고정)
        recent_turns = state.get("chat_history", [])[-10:]
        history_str = (
            "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_turns])
            if recent_turns
            else "없음"
        )

        final_context = f"[최근 대화 기록]\n{history_str}"

        # 현재 MVP에서는 모든 질문에 대해 RAG 도구를 사용하도록 강제합니다.
        return {
            "hybrid_context": final_context,
            "tool_choice": "RAG",
        }

    async def run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """현재 세션에 첨부된 파일에서 RAG 검색을 수행하고 결과를 리랭킹합니다."""
        logger.debug("--- [Node: run_rag_tool] ---")
        question = state["question"]
        session_id = state["session_id"]

        try:
            # TODO: 검색할 문서 개수(k)를 설정 가능하도록 변경 (현재 10개로 고정)
            docs = await self.vector_store.search_session_attachments(
                query=question, session_id=session_id, k=10
            )

            if not docs:
                return {"tool_outputs": {"rag_chunks": []}}

            # 검색 정확도를 높이기 위해 결과 리랭킹
            reranked_docs = self.reranker.rerank(question, docs)

            # 최종적으로 사용할 Top-K 문서 선정
            final_docs = reranked_docs[: state["top_k"]]

            return {"tool_outputs": {"rag_chunks": final_docs}}

        except Exception as e:
            logger.error(f"RAG tool 실행 중 오류 발생: {e}")
            return {"tool_outputs": {"rag_chunks": []}}

    async def generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """모든 컨텍스트를 종합하여 LLM을 통해 최종 답변을 생성합니다."""
        logger.debug("--- [Node: generate_final_answer] ---")

        tool_outputs = state.get("tool_outputs", {})
        rag_chunks = tool_outputs.get("rag_chunks", [])

        # RAG 검색 결과를 프롬프트에 포함할 컨텍스트 문자열로 구성
        if rag_chunks:
            context_str = "[참고 문서]\n" + "\n\n".join(
                [f"- {doc['chunk_text']}" for doc in rag_chunks]
            )
        else:
            context_str = "참고할 문서가 없습니다. 일반적인 지식으로 답변합니다."

        # 최종 프롬프트 생성
        prompt = prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
            hybrid_context=state.get("hybrid_context", ""),
            tool_context=context_str,
            question=state["question"],
            permission_groups="",  # TODO: 사용자 권한 그룹 정보 추가
            user_profile=state.get("user_profile", ""),
        )

        # LLM을 호출하여 답변 스트리밍
        full_answer = ""
        async for chunk in self.llm.stream([HumanMessage(content=prompt)], config={}):
            full_answer += chunk.content

        return {"answer": full_answer}
