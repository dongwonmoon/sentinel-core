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
    def __init__(
        self,
        llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        tools: Dict[str, BaseTool],
    ):
        self.llm = llm
        self.vector_store = vector_store
        self.reranker = reranker

    async def build_hybrid_context(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 1] 컨텍스트 구축
        복잡한 장기 기억, 서사 기억 요약을 제거하고 '최근 대화'에만 집중합니다.
        """
        logger.debug("--- [MVP Node: Simple Context Build] ---")

        # 최근 10개 하드코딩. 추후 개선
        recent_turns = state.get("chat_history", [])[-10:]
        history_str = (
            "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in recent_turns]
            )
            if recent_turns
            else "없음"
        )

        final_context = f"[최근 대화 기록]\n{history_str}"

        # tool_choice는 이제 고정값입니다.
        return {
            "hybrid_context": final_context,
            "tool_choice": "RAG",  # 무조건 RAG 흐름을 타도록 강제
        }

    async def run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2] Session RAG 실행
        현재 세션에 첨부된 파일이 있다면 검색합니다.
        """
        logger.debug("--- [MVP Node: Session RAG] ---")
        question = state["question"]
        session_id = state["session_id"]

        try:
            # 2. 세션 전용 검색 (Session KB)
            # k 하드코딩. 추후 개선
            docs = await self.vector_store.search_session_attachments(
                query=question, session_id=session_id, k=10
            )

            if not docs:
                return {"tool_outputs": {"rag_chunks": []}}

            # 3. 리랭킹 (정확도 향상)
            reranked_docs = self.reranker.rerank(question, docs)

            # 4. Top-K 선정
            final_docs = reranked_docs[: state["top_k"]]

            return {"tool_outputs": {"rag_chunks": final_docs}}

        except Exception as e:
            logger.error(f"RAG 실패: {e}")
            return {"tool_outputs": {"rag_chunks": []}}

    async def generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """
        최종 답변 생성
        """
        logger.debug("--- [MVP Node: Final Answer] ---")

        tool_outputs = state.get("tool_outputs", {})
        rag_chunks = tool_outputs.get("rag_chunks", [])

        # RAG 컨텍스트 조립
        if rag_chunks:
            context_str = "[참고 문서]\n" + "\n\n".join(
                [f"- {doc['chunk_text']}" for doc in rag_chunks]
            )
        else:
            context_str = (
                "참고할 문서가 없습니다. 일반적인 지식으로 답변합니다."
            )

        # 프롬프트 구성
        prompt = prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
            hybrid_context=state.get("hybrid_context", ""),
            tool_context=context_str,
            question=state["question"],
            permission_groups="",
            user_profile=state.get("user_profile", ""),
        )

        # 스트리밍 응답 생성
        full_answer = ""
        async for chunk in self.llm.stream(
            [HumanMessage(content=prompt)], config={}
        ):
            full_answer += chunk.content

        return {"answer": full_answer}
