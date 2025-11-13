from typing import TypedDict, List, Dict, Any, AsyncIterator, Literal, Optional
import json

from langchain_core.messages import HumanMessage
from langchain_core.utils.pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

from .config import Settings
from .llms.base import BaseLLM
from .rerankers.base import BaseReranker
from .store.base import BaseVectorStore
from .store.pg_vector_store import PgVectorStore
from .tools.base import BaseTool
from .logger import get_logger
from . import prompts

logger = get_logger(__name__)


class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의하는 TypedDict입니다.
    그래프의 각 노드를 거치며 이 상태 객체가 업데이트됩니다.
    """

    question: str  # 사용자의 원본 질문
    permission_groups: List[str]  # 사용자의 권한 그룹
    top_k: int  # RAG 검색 시 가져올 최종 청크 수
    doc_ids_filter: Optional[List[str]]

    tool_choice: str  # 라우터가 결정한 도구 이름 ("RAG", "WebSearch", "None")
    tool_outputs: Dict[str, Any]  # 각 도구의 실행 결과를 저장하는 딕셔너리
    code_input: Optional[str] = None

    answer: str  # 최종 답변


class ToolRouter(BaseModel):
    """사용자의 질문에 답하기 위해 사용할 도구를 결정하는 Pydantic 모델입니다."""

    tool_choice: Literal["RAG", "WebSearch", "CodeExecution", "None"] = Field(
        ...,
        description="질문에 답하기 위한 도구 선택. 'RAG' (사내 정보), 'WebSearch' (최신 외부 정보), 'CodeExecution' (계산/분석/코드 실행), 'None' (일반 대화)",
    )


class AgentBrain:
    """
    LangGraph를 사용하여 RAG, 웹 검색, 일반 대화를 조정하는 에이전트의 핵심 로직을 담당합니다.
    """

    def __init__(
        self,
        settings: Settings,
        llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        tools: List[BaseTool],
    ):
        """
        AgentBrain 인스턴스를 초기화합니다.

        Args:
            settings: 애플리케이션 설정 객체
            llm: BaseLLM을 상속받는 언어 모델 객체
            vector_store: BaseVectorStore를 상속받는 벡터 스토어 객체
            reranker: BaseReranker를 상속받는 리랭커 객체
            tools: BaseTool 리스트 (사용할 도구 목록)
        """
        self.settings = settings
        self.llm = llm
        self.vector_store = vector_store
        self.reranker = reranker
        # 도구 이름을 키로 사용하여 쉽게 접근할 수 있도록 딕셔너리로 변환
        self.tools = {tool.name: tool for tool in tools}
        logger.info(
            f"AgentBrain 초기화 완료. 사용 가능 도구: {list(self.tools.keys())}"
        )

        if isinstance(self.vector_store, PgVectorStore):
            self.AsyncSessionLocal = self.vector_store.AsyncSessionLocal
        else:
            logger.warning(
                "감사 로그: PgVectorStore가 아니므로 DB 세션을 가져올 수 없습니다. 로그 저장이 비활성화됩니다."
            )
            self.AsyncSessionLocal = None

        # LangGraph 워크플로우를 빌드하고 컴파일합니다.
        self.graph_app = self._build_graph()

    async def _route_query(self, state: AgentState) -> Dict[str, Any]:
        """LLM을 이용해 질문을 분석하고 사용할 도구를 비동기적으로 결정합니다."""
        logger.debug("--- [Agent Node: Route Query] ---")
        question = state["question"]

        # LLM이 ToolRouter Pydantic 모델에 맞춰 구조화된 출력을 생성하도록 설정
        structured_llm = self.llm.client.with_structured_output(ToolRouter)

        try:
            # LLM을 호출하여 질문에 가장 적합한 도구를 선택
            prompt = prompts.ROUTER_PROMPT_TEMPLATE.format(question=question)
            response = await self.llm.invoke(
                messages=[HumanMessage(content=prompt)],
                config={},
            )
            logger.info(f"라우터 출력: {response.content}")

            response_text = response.content.strip()

            tool_choice = "None"  # 기본값
            if "[RAG]" in response_text:
                tool_choice = "RAG"
            elif "[WebSearch]" in response_text:
                tool_choice = "WebSearch"
            elif "[CodeExecution]" in response_text:
                tool_choice = "CodeExecution"

        except Exception as e:
            # 구조화된 출력에 실패할 경우, 일반 대화로 fallback
            logger.warning(f"라우팅 실패 ({e}). 'None'으로 fallback합니다.")
            tool_choice = "None"

        logger.info(f"라우터 결정: {tool_choice}")
        return {"tool_choice": tool_choice, "tool_outputs": {}}

    async def _run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """'RAG' 도구를 비동기적으로 실행합니다 (Retrieve -> Rerank)."""
        logger.debug("--- [Agent Node: RAG Tool] ---")
        question = state["question"]
        groups = state["permission_groups"]
        doc_ids_filter = state.get("doc_ids_filter")

        # 1. Retrieve: 벡터 스토어에서 관련성 높은 문서를 검색
        retrieved_docs = await self.vector_store.search(
            query=question,
            allowed_groups=groups,
            k=10,  # 리랭킹을 위해 더 많은 후보군(10개)을 검색
            doc_ids_filter=doc_ids_filter,
        )
        if not retrieved_docs:
            return {"tool_outputs": {"rag_chunks": []}}

        # 2. Rerank: 검색된 문서들의 순위를 재조정
        reranked_docs = self.reranker.rerank(question, retrieved_docs)

        # top_k 개수만큼 최종 문서를 선택
        final_docs = reranked_docs[: state["top_k"]]

        # LangChain Document 객체를 직렬화 가능한 딕셔너리로 변환
        final_chunks_as_dict = [
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in final_docs
        ]

        return {"tool_outputs": {"rag_chunks": final_chunks_as_dict}}

    async def _run_web_search_tool(self, state: AgentState) -> Dict[str, Any]:
        """'WebSearch' 도구를 비동기적으로 실행합니다."""
        logger.debug("--- [Agent Node: WebSearch Tool] ---")
        question = state["question"]
        web_search_tool = self.tools.get("duckduckgo_search")

        if not web_search_tool:
            return {
                "tool_outputs": {"search_result": "웹 검색 도구가 설정되지 않았습니다."}
            }

        # DuckDuckGo 비동기 실행
        search_result = await web_search_tool.arun(tool_input=question)
        return {"tool_outputs": {"search_result": search_result}}

    async def _run_code_execution_tool(self, state: AgentState) -> Dict[str, Any]:
        """'CodeExecution' 도구를 비동기적으로 실행합니다."""
        print("--- [Agent Node: CodeExecution Tool] ---")
        question = state["question"]
        code_tool = self.tools.get("python_repl")

        if not code_tool:
            return {
                "tool_outputs": {"code_result": "코드 실행 도구가 설정되지 않았습니다."}
            }

        logger.debug(f"--- Code Gen 프롬프트 전송... ---")
        code_gen_response = await self.llm.invoke(
            messages=[
                HumanMessage(content=prompts.CODE_GEN_PROMPT.format(question=question))
            ],
            config={},
        )

        code_to_run = (
            code_gen_response.content.strip()
            .replace("```python", "```")
            .replace("```", "")
        )
        logger.info(f"--- 실행할 코드 생성:\n{code_to_run}\n---")

        import asyncio

        code_result = await asyncio.to_thread(code_tool.run, tool_input=question)

        # tool_outputs에 'code_result' 키로 저장
        tool_outputs = state.get("tool_outputs", {})
        tool_outputs["code_result"] = str(code_result)  # 결과를 문자열로 저장
        return {"tool_outputs": tool_outputs, "code_input": code_to_run}

    async def _generate_final_answer(
        self, state: AgentState
    ) -> AsyncIterator[Dict[str, Any]]:
        """모든 도구의 결과를 취합하여 최종 답변을 비동기 스트리밍으로 생성합니다."""
        logger.debug("--- [Agent Node: Stream Generate] ---")
        question = state["question"]
        tool_choice = state.get("tool_choice")
        tool_outputs = state.get("tool_outputs", {})

        # 1. 컨텍스트 준비
        context = ""
        rag_chunks = tool_outputs.get("rag_chunks")
        search_result = tool_outputs.get("search_result")

        code_input = state.get("code_input")
        code_result = tool_outputs.get("code_result")

        if tool_choice == "RAG" and rag_chunks:
            context_docs = [chunk["page_content"] for chunk in rag_chunks]
            context = "\n\n---\n\n".join(context_docs)
            context = f"[사내 RAG 정보]\n{context}"
        elif tool_choice == "WebSearch" and search_result:
            context = f"[웹 검색 결과]\n{search_result}"
        elif tool_choice == "CodeExecution" and code_result:
            context = f"[실행된 코드]\n{code_input}\n\n[코드 실행 결과]\n{code_result}"
        elif tool_choice == "None":
            context = "도움말: 일반 대화 모드입니다."
        else:
            context = "도움말: 관련 정보를 찾지 못했습니다."

        # 2. 프롬프트 생성 및 LLM 스트리밍 호출
        messages = [
            HumanMessage(
                content=prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
                    context=context,
                    question=question,
                    permission_groups=state.get("permission_groups", ["N/A"]),
                )
            )
        ]

        full_answer = ""

        async for chunk in self.llm.stream(messages, config={}):
            full_answer += chunk.content
            yield {"answer": chunk.content}

        state["answer"] = full_answer

    async def _save_audit_log(self, state: AgentState) -> Dict[str, Any]:
        """최종 상태를 agent_audit_log 테이블에 비동기적으로 저장합니다."""
        logger.debug("--- [Agent Node: Save Audit Log] ---")

        if not self.AsyncSessionLocal:
            logger.warning("감사 로그 저장을 건너뜁니다 (DB 세션 사용 불가).")
            return {}

        try:
            # 상태 객체(TypedDict)를 DB에 저장하기 쉬운 dict로 복사
            # JSONB에 저장하기 위해 state 자체를 직렬화 가능한 dict로 만듭니다.
            # (주의: Pydantic 모델이 아니므로 직접 직렬화 시도)
            try:
                state_json_str = json.dumps(state)
            except TypeError as e:
                logger.error(f"AgentState 직렬화 실패: {e}. 일부만 저장합니다.")
                state_json_str = json.dumps({"error": "state serialization failed"})

            log_data = {
                "session_id": None,  # (추후 세션 기능이 생기면 채움)
                "question": state.get("question", "N/A"),
                "permission_groups": state.get("permission_groups", []),
                "tool_choice": state.get("tool_choice", "N/A"),
                "code_input": state.get("code_input"),
                "final_answer": state.get(
                    "answer", ""
                ),  # _generate_final_answer에서 채워줌
                "full_agent_state": json.dumps(state_json_str),  # JSON 문자열로 저장
            }

            # 비동기 세션을 사용하여 DB에 저장
            from sqlalchemy import text

            async with self.AsyncSessionLocal() as session:
                async with session.begin():
                    stmt_log_insert = text(
                        """
                        INSERT INTO agent_audit_log 
                        (session_id, question, permission_groups, tool_choice, code_input, final_answer, full_agent_state)
                        VALUES (:session_id, :question, :permission_groups, :tool_choice, :code_input, :final_answer, :full_agent_state)
                    """
                    )
                    await session.execute(stmt_log_insert, log_data)

            logger.info(f"감사 로그 저장 완료 (Q: {log_data['question'][:20]}...)")

        except Exception as e:
            # 로그 저장에 실패해도 사용자 응답은 중단되면 안 됨
            logger.error(f"감사 로그 저장 실패: {e}", exc_info=True)

        return {}

    def _decide_branch(
        self, state: AgentState
    ) -> Literal["RAG", "WebSearch", "CodeExecution", "None"]:
        """라우터의 결정('tool_choice')에 따라 그래프를 분기합니다."""
        choice = state["tool_choice"]
        if choice not in ["RAG", "WebSearch", "CodeExecution", "None"]:
            return "None"
        return choice

    def _build_graph(self) -> StateGraph:
        """조건부 라우팅을 포함하는 LangGraph 워크플로우를 구성합니다."""
        workflow = StateGraph(AgentState)

        # 1. 노드 등록
        workflow.add_node("route_query", self._route_query)
        workflow.add_node("run_rag_tool", self._run_rag_tool)
        workflow.add_node("run_web_search_tool", self._run_web_search_tool)
        workflow.add_node("run_code_execution_tool", self._run_code_execution_tool)
        workflow.add_node("generate_final_answer", self._generate_final_answer)
        workflow.add_node("save_audit_log", self._save_audit_log)

        # 2. 진입점 설정
        workflow.set_entry_point("route_query")

        # 3. 조건부 엣지 (라우팅)
        workflow.add_conditional_edges(
            "route_query",
            self._decide_branch,
            {
                "RAG": "run_rag_tool",
                "WebSearch": "run_web_search_tool",
                "CodeExecution": "run_code_execution_tool",
                "None": "generate_final_answer",
            },
        )

        # 4. 일반 엣지 (도구 실행 후 답변 생성으로)
        workflow.add_edge("run_rag_tool", "generate_final_answer")
        workflow.add_edge("run_web_search_tool", "generate_final_answer")
        workflow.add_edge("run_code_execution_tool", "generate_final_answer")
        workflow.add_edge("generate_final_answer", "save_audit_log")
        workflow.add_edge("save_audit_log", END)

        # 5. 그래프 컴파일
        return workflow.compile()
