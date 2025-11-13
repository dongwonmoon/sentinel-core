"""
핵심 에이전트(Agent) 로직을 담당하는 모듈입니다.
LangGraph를 사용하여 RAG, 웹 검색, 코드 실행 등 다양한 도구를 조정합니다.
"""
import json
from typing import TypedDict, List, Dict, Any, AsyncIterator, Literal, Optional

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

# --- 1. 아키텍처에 따른 임포트 경로 수정 ---
from .config import Settings
from . import prompts
from .logger import get_logger
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.vector_stores.base import BaseVectorStore
from ..components.tools.base import BaseTool


logger = get_logger(__name__)


# --- 2. Agent 상태 및 유틸리티 함수 정의 ---

class AgentState(TypedDict):
    """
    LangGraph의 상태를 정의합니다. 그래프의 각 노드를 거치며 이 상태가 업데이트됩니다.
    """
    # 입력
    question: str
    permission_groups: List[str]
    top_k: int
    doc_ids_filter: Optional[List[str]]
    chat_history: List[Dict[str, str]]

    # 중간 상태
    chosen_llm: Literal["fast", "powerful"]
    tool_choice: str
    tool_outputs: Dict[str, Any]
    code_input: Optional[str] = None

    # 최종 출력
    answer: str


def _convert_history_dicts_to_messages(
    history_dicts: List[Dict[str, str]],
) -> List[BaseMessage]:
    """채팅 기록(딕셔너리 리스트)을 LangChain 메시지 객체 리스트로 변환합니다."""
    messages = []
    for msg in history_dicts:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content", "")))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg.get("content", "")))
    return messages


# --- 3. 핵심 Agent 클래스 ---

class Agent:
    """
    LangGraph를 사용하여 RAG, 웹 검색 등을 조정하는 에이전트의 핵심 로직.
    (기존 AgentBrain 클래스)
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
        self.llm_fast = fast_llm
        self.llm_powerful = powerful_llm
        self.vector_store = vector_store
        self.reranker = reranker
        self.tools = {tool.name: tool for tool in tools}
        logger.info(f"Agent 초기화 완료. 사용 가능 도구: {list(self.tools.keys())}")

        # LangGraph 워크플로우 빌드 및 컴파일
        self.graph_app = self._build_graph()

    # --- 3-1. 새로운 Public 메서드 (API 계층에서 호출) ---

    async def stream_response(
        self,
        inputs: Dict[str, Any],
        db_session: AsyncSession
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        답변 생성을 스트리밍하고, 완료 후 감사 로그를 저장하는 새로운 메인 메서드.
        """
        final_state = None
        # LangGraph의 astream_events를 사용하여 각 노드의 이벤트를 스트리밍
        async for event in self.graph_app.astream_events(inputs, version="v1"):
            yield event  # 이벤트를 호출자(API 엔드포인트)에게 그대로 전달
            
            # 스트림의 마지막 이벤트에서 최종 상태를 저장
            if event["event"] == "on_graph_end":
                final_state = event["data"]["output"]

        # 스트리밍이 모두 끝난 후, 최종 상태를 사용하여 감사 로그를 저장
        if final_state:
            try:
                await self.save_audit_log(final_state, db_session)
            except Exception as e:
                # 로그 저장에 실패해도 사용자 응답은 이미 완료되었으므로, 에러 로깅만 처리
                logger.error(f"감사 로그 저장 실패: {e}", exc_info=True)

    async def save_audit_log(self, state: AgentState, db_session: AsyncSession):
        """
        최종 상태와 DB 세션을 받아 감사 로그를 비동기적으로 저장합니다.
        """
        logger.debug("--- [Agent Side-Effect: Save Audit Log] ---")
        
        try:
            # 상태 객체를 JSON으로 직렬화
            state_json_str = json.dumps(state, default=str) # datetime 등 직렬화 안되는 타입 에러 방지
        except TypeError as e:
            logger.error(f"AgentState 직렬화 실패: {e}. 일부만 저장합니다.")
            state_json_str = json.dumps({"error": "state serialization failed"})

        log_data = {
            "session_id": None,  # TODO: 추후 세션 기능 구현 시 채워넣기
            "question": state.get("question", "N/A"),
            "permission_groups": state.get("permission_groups", []),
            "tool_choice": state.get("tool_choice", "N/A"),
            "code_input": state.get("code_input"),
            "final_answer": state.get("answer", ""),
            "full_agent_state": state_json_str,
        }

        from sqlalchemy import text
        async with db_session.begin():
            stmt = text(
                """
                INSERT INTO agent_audit_log 
                (session_id, question, permission_groups, tool_choice, code_input, final_answer, full_agent_state)
                VALUES (:session_id, :question, :permission_groups, :tool_choice, :code_input, :final_answer, :full_agent_state::jsonb)
                """
            )
            await db_session.execute(stmt, log_data)
        
        logger.info(f"감사 로그 저장 완료 (Q: {log_data['question'][:20]}...)")


    # --- 3-2. LangGraph 노드 정의 ---

    async def _route_query(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드] LLM을 이용해 질문을 분석하고 사용할 도구를 결정합니다.
        (개선 제안: 현재는 문자열 파싱 방식. 안정성을 위해 LLM의 Tool Calling 기능으로 개선 가능)
        """
        logger.debug("--- [Agent Node: Route Query] ---")
        question = state["question"]
        history = _convert_history_dicts_to_messages(state.get("chat_history", []))
        prompt = prompts.ROUTER_PROMPT_TEMPLATE.format(
            history="\n".join([f"{m.type}: {m.content}" for m in history]),
            question=question,
        )

        response = await self.llm_fast.invoke([HumanMessage(content=prompt)])
        
        # LLM의 응답을 파싱하여 라우팅 결정 (오류에 취약할 수 있음)
        try:
            decision_text = response.content.strip().replace("[", "").replace("]", "")
            llm_part, tool_part = [part.strip() for part in decision_text.split(",")]
            chosen_llm = "powerful" if "powerful" in llm_part.lower() else "fast"
            tool_choice = tool_part if tool_part in ["RAG", "WebSearch", "CodeExecution", "None"] else "None"
        except Exception as e:
            logger.warning(f"라우터 출력 파싱 실패 ({e}). [fast, None]으로 Fallback.")
            chosen_llm, tool_choice = "fast", "None"

        logger.info(f"라우터 결정 -> LLM: {chosen_llm}, 도구: {tool_choice}")
        return {"chosen_llm": chosen_llm, "tool_choice": tool_choice, "tool_outputs": {}}

    async def _run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 'RAG' 도구를 실행합니다 (Retrieve -> Rerank)."""
        logger.debug("--- [Agent Node: RAG Tool] ---")
        retrieved = await self.vector_store.search(
            query=state["question"],
            allowed_groups=state["permission_groups"],
            k=10,
            doc_ids_filter=state.get("doc_ids_filter"),
        )
        if not retrieved:
            return {"tool_outputs": {"rag_chunks": []}}

        reranked = self.reranker.rerank(state["question"], retrieved)
        final_docs = reranked[: state["top_k"]]
        
        dict_docs = [{"page_content": doc.page_content, "metadata": doc.metadata, "score": score} for doc, score in final_docs]
        return {"tool_outputs": {"rag_chunks": dict_docs}}

    async def _run_web_search_tool(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 'WebSearch' 도구를 실행합니다."""
        logger.debug("--- [Agent Node: WebSearch Tool] ---")
        tool = self.tools.get("duckduckgo_search")
        if not tool:
            return {"tool_outputs": {"search_result": "웹 검색 도구가 설정되지 않았습니다."}}
        
        result = await tool.arun(tool_input=state["question"])
        return {"tool_outputs": {"search_result": result}}

    async def _run_code_execution_tool(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 'CodeExecution' 도구를 실행합니다."""
        logger.debug("--- [Agent Node: CodeExecution Tool] ---")
        tool = self.tools.get("python_repl")
        if not tool:
            return {"tool_outputs": {"code_result": "코드 실행 도구가 설정되지 않았습니다."}}

        # 1. Powerful LLM으로 실행할 코드 생성
        code_gen_prompt = prompts.CODE_GEN_PROMPT.format(question=state["question"])
        response = await self.llm_powerful.invoke([HumanMessage(content=code_gen_prompt)])
        code_to_run = response.content.strip().replace("```python", "").replace("```", "")
        logger.info(f"--- 실행할 코드 생성:\n{code_to_run}\n---")

        # 2. 생성된 코드 실행 (동기 함수이므로 스레드에서 실행)
        import asyncio
        code_result = await asyncio.to_thread(tool.run, tool_input=code_to_run)
        
        tool_outputs = state.get("tool_outputs", {})
        tool_outputs["code_result"] = str(code_result)
        return {"tool_outputs": tool_outputs, "code_input": code_to_run}

    async def _generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 모든 컨텍스트를 종합하여 최종 답변을 생성합니다."""
        logger.debug("--- [Agent Node: Generate Final Answer] ---")
        llm = self.llm_powerful if state.get("chosen_llm") == "powerful" else self.llm_fast
        
        # 컨텍스트 구성
        context_str = ""
        if state["tool_choice"] == "RAG" and state["tool_outputs"].get("rag_chunks"):
            docs = [chunk["page_content"] for chunk in state["tool_outputs"]["rag_chunks"]]
            context_str = "[사내 RAG 정보]\n" + "\n\n---\n\n".join(docs)
        # ... 다른 도구 결과에 대한 컨텍스트 구성 ...
        
        history = _convert_history_dicts_to_messages(state.get("chat_history", []))
        prompt = prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
            context=context_str, question=state["question"]
        )
        messages = history + [HumanMessage(content=prompt)]

        # 답변 스트리밍
        full_answer = ""
        async for chunk in llm.stream(messages):
            full_answer += chunk.content
            # 스트리밍 구현은 API 계층에서 이뤄지므로, 여기서는 최종 답변만 집계
        
        return {"answer": full_answer}

    # --- 3-3. LangGraph 빌드 ---

    def _decide_branch(self, state: AgentState) -> str:
        """라우터의 결정에 따라 그래프를 분기합니다."""
        return state.get("tool_choice", "None")

    def _build_graph(self) -> StateGraph:
        """조건부 라우팅을 포함하는 LangGraph 워크플로우를 구성합니다."""
        workflow = StateGraph(AgentState)

        # 노드 등록
        workflow.add_node("route_query", self._route_query)
        workflow.add_node("run_rag_tool", self._run_rag_tool)
        workflow.add_node("run_web_search_tool", self._run_web_search_tool)
        workflow.add_node("run_code_execution_tool", self._run_code_execution_tool)
        workflow.add_node("generate_final_answer", self._generate_final_answer)

        # 엣지 연결
        workflow.set_entry_point("route_query")
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
        workflow.add_edge("run_rag_tool", "generate_final_answer")
        workflow.add_edge("run_web_search_tool", "generate_final_answer")
        workflow.add_edge("run_code_execution_tool", "generate_final_answer")
        
        # 감사 로그 노드를 제거하고, 답변 생성 후 그래프가 종료되도록 변경
        workflow.add_edge("generate_final_answer", END)

        return workflow.compile()