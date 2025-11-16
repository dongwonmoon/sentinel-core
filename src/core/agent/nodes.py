# -*- coding: utf-8 -*-
"""
Agent의 각 노드(Node)에 대한 실제 실행 로직을 정의합니다.

이 파일의 `AgentNodes` 클래스는 LangGraph 워크플로우의 각 단계를 구성하는
메서드들을 포함합니다. 각 메서드는 `AgentState`를 입력으로 받아 특정 작업을
수행하고, 그 결과를 담은 딕셔너리를 반환하여 상태(State)를 업데이트합니다.
이러한 방식은 각 노드의 역할을 명확히 분리하고, 테스트와 유지보수를 용이하게 합니다.
"""

import asyncio
import json
from typing import Any, Dict, List

import httpx
from langchain_core.messages import HumanMessage
from sqlalchemy import text

from ...db import models
from ...components.llms.base import BaseLLM
from ...components.rerankers.base import BaseReranker
from ...components.tools.base import BaseTool
from ...components.vector_stores.base import BaseVectorStore
from .. import prompts
from ..logger import get_logger
from .state import AgentState, DynamicTool

logger = get_logger(__name__)

# 외부 API 호출을 위한 비동기 HTTP 클라이언트.
# 애플리케이션 전체에서 재사용하여 효율성을 높입니다.
http_client = httpx.AsyncClient(timeout=10.0)


class AgentNodes:
    """
    Agent 그래프의 각 노드에 대한 실행 로직을 담고 있는 클래스입니다.
    각종 LLM, 벡터 저장소, 도구 등을 생성자에서 주입받아 사용합니다.
    이는 의존성 주입(Dependency Injection) 패턴으로, 테스트 용이성과 유연성을 높입니다.
    """

    def __init__(
        self,
        fast_llm: BaseLLM,
        powerful_llm: BaseLLM,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        tools: Dict[str, BaseTool],
    ):
        """
        AgentNodes를 초기화합니다.

        Args:
            fast_llm: 빠른 응답이 필요한 작업(라우팅 등)에 사용될 LLM.
            powerful_llm: 복잡한 추론, 코드 생성 등에 사용될 고성능 LLM.
            vector_store: 문서 검색을 위한 벡터 저장소.
            reranker: 검색 결과의 순위를 재조정하는 리랭커.
            tools: 에이전트가 사용할 수 있는 정적 도구(웹 검색, 코드 실행 등) 딕셔너리.
        """
        self.llm_fast = fast_llm
        self.llm_powerful = powerful_llm
        self.vector_store = vector_store
        self.reranker = reranker
        self.tools = tools

        # DB 접근이 필요한 노드를 위해, vector_store에서 DB 세션 팩토리를 가져옵니다.
        # 이는 vector_store가 DB 연결 정보를 중앙에서 관리하고 있음을 전제합니다.
        self.AsyncSessionLocal = getattr(vector_store, "AsyncSessionLocal", None)
        if not self.AsyncSessionLocal:
            logger.warning(
                "AgentNodes: DB 세션 팩토리를 찾을 수 없습니다. 'long_term_memory' 및 'dynamic_tools' 기능이 비활성화됩니다."
            )

    async def build_hybrid_context(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 0: 하이브리드 컨텍스트 구축] - 그래프의 진입점(Entrypoint).
        사용자 질문에 답변하기 전에, 다양한 소스에서 관련 정보를 병렬로 수집하여
        '하이브리드 컨텍스트'를 구축합니다. 이는 LLM이 더 풍부한 맥락을 바탕으로
        정확하고 개인화된 답변을 생성하도록 돕는 핵심 단계입니다.

        수집하는 정보의 종류:
        A. 단기 기억 (Short-Term Memory): 최근 대화 몇 턴을 그대로 가져와 대화의 흐름을 파악합니다.
        B. 서사 기억 (Narrative Memory): 전체 대화 기록을 요약하여 장기적인 대화의 맥락을 유지합니다.
        C. 장기 기억 (Long-Term Memory): 현재 질문과 관련성이 높은 '과거의 특정 대화'를 RAG로 인출하여,
           과거의 중요한 정보를 상기시킵니다. (일명 '사건 기억')
        D. 동적 도구 (Dynamic Tools): 현재 사용자의 권한으로 접근 가능한 외부 도구 목록을 DB에서 가져옵니다.

        이러한 다층적 메모리 접근 방식은 에이전트가 단순한 Q&A를 넘어,
        지속적인 대화 속에서 맥락을 이해하고 과거 정보를 활용하는 고차원적인 상호작용을 가능하게 합니다.

        Returns:
            Dict[str, Any]: 'hybrid_context'와 'available_dynamic_tools'를 포함하는 상태 업데이트 딕셔너리.
        """
        logger.debug("--- [Agent Node: Build Hybrid Context] ---")

        async def get_short_term_memory() -> str:
            """A. 최근 3개의 대화만 원본 그대로 가져옵니다."""
            try:
                recent_turns = state.get("chat_history", [])[-3:]
                if not recent_turns:
                    return ""
                history_str = "\n".join(
                    [f"{msg['role']}: {msg['content']}" for msg in recent_turns]
                )
                logger.debug(
                    f"하이브리드 컨텍스트(A): 최근 대화 {len(recent_turns)}개 로드."
                )
                return f"[최근 대화]\n{history_str}"
            except Exception as e:
                logger.warning(f"하이브리드 컨텍스트(A) 로드 실패: {e}")
                return ""

        async def get_narrative_memory() -> str:
            """B. 전체 대화의 맥락을 요약하여, LLM이 긴 대화의 핵심을 놓치지 않도록 돕습니다."""
            try:
                full_history = state.get("chat_history", [])
                if len(full_history) < 5:  # 대화가 짧으면 요약 불필요
                    return ""
                history_str = "\n".join(
                    [f"{msg['role']}: {msg['content']}" for msg in full_history]
                )
                prompt = prompts.MEMORY_SUMMARY_PROMPT_TEMPLATE.format(
                    history=history_str, question=state["question"]
                )
                response = await self.llm_fast.invoke(
                    [HumanMessage(content=prompt)], config={}
                )
                summary = response.content.strip()
                logger.debug("하이브리드 컨텍스트(B): 대화 요약 생성 완료.")
                return f"[대화 요약]\n{summary}"
            except Exception as e:
                logger.warning(f"하이브리드 컨텍스트(B) 요약 실패: {e}")
                return ""

        async def get_long_term_memory() -> str:
            """C. 현재 질문과 관련성이 높은 '과거의 특정 대화'를 RAG로 인출합니다. (일명 '사건 기억')"""
            if not self.AsyncSessionLocal:
                return ""
            try:
                query_embedding = self.vector_store.embedding_model.embed_query(
                    state["question"]
                )
                sql_query = """
                    SELECT turn_text, embedding <-> :query_embedding AS distance
                    FROM chat_turn_memory
                    WHERE session_id = :session_id AND user_id = :user_id
                    ORDER BY distance
                    LIMIT 2
                """
                async with self.AsyncSessionLocal() as session:
                    result = await session.execute(
                        text(sql_query),
                        {
                            "query_embedding": str(query_embedding),
                            "session_id": state["session_id"],
                            "user_id": int(state["user_id"]),
                        },
                    )
                    relevant_turns = [
                        row.turn_text for row in result if row.distance < 0.8
                    ]
                if not relevant_turns:
                    return ""
                logger.debug(
                    f"하이브리드 컨텍스트(C): 관련 '사건 기억' {len(relevant_turns)}개 인출."
                )
                return f"[관련 과거 기억 (RAG)]\n" + "\n---\n".join(relevant_turns)
            except Exception as e:
                logger.warning(f"하이브리드 컨텍스트(C) 인출 실패: {e}", exc_info=True)
                return ""

        async def get_available_dynamic_tools() -> List[DynamicTool]:
            """D. 사용자의 권한 그룹과 일치하는 '동적 도구'를 DB에서 로드합니다."""
            if not self.AsyncSessionLocal:
                return []
            try:
                sql_query = """
                    SELECT name, description, api_endpoint_url, json_schema, permission_groups
                    FROM registered_tools
                    WHERE is_active = true
                    AND permission_groups && :allowed_groups
                """
                async with self.AsyncSessionLocal() as session:
                    result = await session.execute(
                        text(sql_query),
                        {"allowed_groups": state["permission_groups"]},
                    )
                    tools = [DynamicTool(**row._asdict()) for row in result]
                logger.debug(f"하이브리드 컨텍스트(D): 동적 도구 {len(tools)}개 로드.")
                return tools
            except Exception as e:
                logger.warning(
                    f"하이브리드 컨텍스트(D) 도구 로드 실패: {e}", exc_info=True
                )
                return []

        # 4가지 정보 수집 작업을 병렬로 실행하여 응답 시간을 단축합니다.
        results = await asyncio.gather(
            get_short_term_memory(),
            get_narrative_memory(),
            get_long_term_memory(),
            get_available_dynamic_tools(),
        )

        # 수집된 텍스트 정보들을 하나의 컨텍스트 문자열로 조합합니다.
        final_hybrid_context = "\n\n".join(
            filter(None, results[:-1])
        )  # 비어있지 않은 결과만 합침
        available_dynamic_tools = results[-1]

        if not final_hybrid_context:
            final_hybrid_context = "도움말: 첫 대화입니다."

        return {
            "hybrid_context": final_hybrid_context,
            "available_dynamic_tools": available_dynamic_tools,
        }

    async def route_query(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 1: 라우터] LLM을 이용해 사용자의 질문을 분석하고, 가장 적절한 도구를 결정합니다.

        이 노드는 에이전트의 "두뇌" 역할을 하여, 질문의 의도를 파악하고
        다음에 어떤 작업을 수행할지 결정하는 분기점입니다. 'fast' LLM을 사용하여 응답 시간을 최소화합니다.

        Args:
            state (AgentState): 현재 에이전트의 상태. 'question', 'hybrid_context' 등을 포함.

        Returns:
            Dict[str, Any]: 'chosen_llm', 'tool_choice' 등 라우팅 결정 정보를 포함한 상태 업데이트 딕셔너리.
        """
        logger.debug("--- [Agent Node: Route Query] ---")
        question = state["question"]
        context = state["hybrid_context"]

        # LLM에게 제공할 프롬프트를 구성합니다. 사용 가능한 정적/동적 도구 목록을 명시합니다.
        static_tools_desc = [tool.to_tool_string() for name, tool in self.tools.items()]
        dynamic_tools = state.get("available_dynamic_tools", [])
        dynamic_tools_desc = [tool.to_tool_string() for tool in dynamic_tools]

        # 동적 도구를 선택했을 때 따라야 할 JSON 출력 형식을 명확히 지시합니다.
        dynamic_tool_names = [tool.name for tool in dynamic_tools]
        dynamic_tool_format_instruction = ""
        if dynamic_tools:
            dynamic_tool_format_instruction = (
                f"\n[IMPORTANT] '{dynamic_tool_names}' 중 하나를 선택한 경우,"
                "반드시 다음 JSON 포맷으로 인자(argument)를 함께 출력해야 합니다:\n"
                '{"tool": "선택한_도구_이름", "args": {"인자1": "값1", "인자2": "값2"}}'
            )

        # 라우팅 결정을 위한 프롬프트를 생성합니다.
        prompt = prompts.ROUTER_PROMPT_TEMPLATE.format(
            context=context,
            static_tools="\n".join(static_tools_desc),
            dynamic_tools="\n".join(dynamic_tools_desc),
            dynamic_tool_format=dynamic_tool_format_instruction,
            question=question,
            failed_tools=state.get("failed_tools", []),
        )

        # 'fast' LLM을 호출하여 신속하게 도구를 결정합니다.
        response = await self.llm_fast.invoke([HumanMessage(content=prompt)], config={})
        response_content = response.content.strip()
        logger.debug(f"라우터 응답: {response_content}")

        try:
            # 응답이 JSON 형식이면 동적 도구 호출로 간주합니다.
            if response_content.startswith("{"):
                logger.debug("라우터 응답이 JSON(동적 도구) 포맷입니다.")
                tool_call_data = json.loads(response_content)
                tool_name = tool_call_data.get("tool")
                tool_args = tool_call_data.get("args")

                # LLM이 반환한 도구 이름이 실제 사용 가능한 동적 도구인지 확인합니다.
                tool_to_call = next(
                    (t for t in dynamic_tools if t.name == tool_name), None
                )

                if tool_to_call and isinstance(tool_args, dict):
                    logger.info(f"라우터 결정 -> 동적 도구: {tool_name}")
                    return {
                        "chosen_llm": "fast",
                        "tool_choice": "DynamicTool",
                        "dynamic_tool_to_call": tool_to_call,
                        "dynamic_tool_input": tool_args,
                        "tool_outputs": {},
                    }
                else:
                    logger.warning(
                        f"LLM이 유효하지 않은 동적 도구({tool_name}) 또는 인자({tool_args})를 선택했습니다."
                    )
                    raise ValueError("Invalid dynamic tool call")

            # 기존 정적 도구 포맷([LLM, TOOL])인지 확인합니다.
            logger.debug("라우터 응답이 정적 도구 포맷입니다.")
            decision_text = response_content.replace("[", "").replace("]", "")
            llm_part, tool_part = [part.strip() for part in decision_text.split(",")]

            chosen_llm = "powerful" if "powerful" in llm_part.lower() else "fast"
            tool_choice = (
                tool_part
                if tool_part in ["RAG", "WebSearch", "CodeExecution", "None"]
                else "None"
            )

            logger.info(f"라우터 결정 -> LLM: {chosen_llm}, 정적 도구: {tool_choice}")
            return {
                "chosen_llm": chosen_llm,
                "tool_choice": tool_choice,
                "tool_outputs": {},
            }

        except Exception as e:
            # LLM의 출력을 파싱하는 데 실패할 경우, 안전하게 '도구 없음'으로 처리합니다.
            # 이는 에이전트가 예기치 않은 LLM 응답에도 중단되지 않고 계속 작동하도록 보장하는
            # 매우 중요한 예외 처리(Fallback) 로직입니다.
            logger.warning(
                f"라우터 출력 파싱 실패 ({e}). [fast, None]으로 Fallback. 원본: {response_content}"
            )
            return {
                "chosen_llm": "fast",
                "tool_choice": "None",
                "tool_outputs": {},
            }

    async def run_dynamic_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-D: 동적 도구 실행] 'DynamicTool'로 라우팅되었을 때,
        DB에 등록된 API 엔드포인트를 호출하여 외부 기능을 수행합니다.
        이 노드는 데이터베이스에 새로운 도구를 등록하는 것만으로 에이전트의 능력을
        코드 변경 없이 확장할 수 있게 해주는 강력한 아키텍처 패턴입니다.

        Args:
            state (AgentState): `dynamic_tool_to_call`과 `dynamic_tool_input`을 포함.

        Returns:
            Dict[str, Any]: 도구 실행 결과를 `tool_outputs`에 담아 반환.
        """
        logger.debug("--- [Agent Node: Dynamic Tool] ---")
        tool_to_call: DynamicTool = state.get("dynamic_tool_to_call")
        tool_input: Dict[str, Any] = state.get("dynamic_tool_input")

        if not tool_to_call or not isinstance(tool_input, dict):
            logger.error(
                "DynamicTool 실행 실패: 도구 정보 또는 입력값이 AgentState에 없습니다."
            )
            return {
                "tool_outputs": {
                    "dynamic_tool_result": "Error: Tool information missing."
                }
            }

        tool_name = tool_to_call.name
        endpoint_url = str(tool_to_call.api_endpoint_url)

        logger.info(
            f"동적 도구 '{tool_name}' 실행 시작. 엔드포인트: {endpoint_url}, 인자: {tool_input}"
        )

        try:
            # (향후 이 부분에 OAuth2 등 기업 내부 인증 헤더 추가 가능)
            response = await http_client.post(endpoint_url, json=tool_input)
            response.raise_for_status()  # 4xx, 5xx 에러 시 예외 발생

            result_data = response.json()
            # LLM이 이해할 수 있도록 결과를 JSON 문자열로 변환하여 반환합니다.
            result_str = json.dumps(result_data)

            logger.info(
                f"동적 도구 '{tool_name}' 실행 성공. 결과(일부): {result_str[:200]}..."
            )
            return {"tool_outputs": {"dynamic_tool_result": result_str}}

        except httpx.HTTPStatusError as e:
            error_message = f"Error: API call failed with status {e.response.status_code}. Details: {e.response.text}"
            logger.warning(f"동적 도구 '{tool_name}' API 호출 실패: {error_message}")
            return {"tool_outputs": {"dynamic_tool_result": error_message}}
        except Exception as e:
            error_message = f"Error: An unexpected error occurred: {e}"
            logger.error(
                f"동적 도구 '{tool_name}' 실행 중 예기치 않은 오류: {e}",
                exc_info=True,
            )
            return {"tool_outputs": {"dynamic_tool_result": error_message}}

    async def run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-A: 듀얼 RAG] 'Global KB'(전사적 영구 지식)와 'Session KB'(세션 한정 임시 지식)를
        `asyncio.gather`를 통해 *동시에* 검색하고, `reranker`로 결과를 병합하여
        질문과 가장 관련성 높은 최상의 컨텍스트를 생성합니다.

        이 '듀얼 RAG' 접근법은 에이전트가 공식적인 정보와 대화 중에 업로드된
        비공식적인 정보를 모두 활용하여 답변할 수 있게 하는 강력한 기능입니다.
        """
        logger.debug("--- [Agent Node: 듀얼 RAG Tool] ---")
        question = state["question"]
        query_embedding = self.vector_store.embedding_model.embed_query(question)

        try:
            # 두 개의 검색 작업을 병렬로 실행하여 응답 시간을 최적화합니다.
            results = await asyncio.gather(
                # 1. Global KB 검색 (영구, 권한 필터링 적용)
                self.vector_store.search(
                    query_embedding=query_embedding,
                    allowed_groups=state["permission_groups"],
                    k=5,
                    doc_ids_filter=state.get("doc_ids_filter"),
                ),
                # 2. Session KB 검색 (임시, 현재 세션 ID로 필터링)
                self.vector_store.search_session_attachments(
                    query_embedding=query_embedding,
                    session_id=state["session_id"],
                    k=5,
                ),
            )
            global_docs, session_docs = results
            logger.debug(
                f"듀얼 RAG 검색 완료: Global {len(global_docs)}건, Session {len(session_docs)}건"
            )

            all_retrieved_docs: List[Dict[str, Any]] = global_docs + session_docs

            if not all_retrieved_docs:
                logger.info("듀얼 RAG 검색 결과 없음 - 질문='%s'", question[:80])
                failed = state.get("failed_tools", []) + ["RAG"]
                return {
                    "tool_outputs": {"rag_chunks": []},
                    "failed_tools": failed,
                }

            # 3. Reranker로 모든 검색 결과를 재정렬하여 가장 관련성 높은 문서를 상위로 올립니다.
            reranked_docs = self.reranker.rerank(question, all_retrieved_docs)

            # 4. 최종적으로 LLM에 전달할 상위 K개의 문서를 선택합니다.
            final_docs = reranked_docs[: state["top_k"]]
            logger.info(
                "듀얼 RAG 리랭킹 완료 - 원본 %d건, 최종 %d건 선택",
                len(all_retrieved_docs),
                len(final_docs),
            )

            return {"tool_outputs": {"rag_chunks": final_docs}}

        except Exception as e:
            logger.error(f"듀얼 RAG 실행 중 오류 발생: {e}", exc_info=True)
            failed = state.get("failed_tools", []) + ["RAG"]
            return {"tool_outputs": {"rag_chunks": []}, "failed_tools": failed}

    async def run_web_search_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-B: 웹 검색] 'WebSearch' 도구(DuckDuckGo)를 실행하여 웹 검색을 수행합니다.
        RAG로 답변을 찾지 못했을 때 최신 정보나 외부 사실을 찾는 데 사용됩니다.
        """
        logger.debug("--- [Agent Node: WebSearch Tool] ---")
        tool = self.tools.get("duckduckgo_search")
        if not tool:
            logger.warning(
                "웹 검색 도구 미설정 - 'duckduckgo_search' 키를 찾을 수 없음"
            )
            return {
                "tool_outputs": {"search_result": "웹 검색 도구가 설정되지 않았습니다."}
            }

        result = await tool.arun(tool_input=state["question"])
        return {"tool_outputs": {"search_result": result}}

    async def run_code_execution_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-C: 코드 실행] 'CodeExecution' 도구를 3단계에 걸쳐 실행합니다.
        1. **컨텍스트 검색**: RAG를 통해 질문과 관련된 내부 코드 컨텍스트(예: 다른 함수, 클래스)를 검색합니다.
        2. **코드 생성**: 'powerful' LLM을 사용하여 검색된 컨텍스트 기반으로 실행할 Python 코드를 생성합니다.
        3. **코드 실행**: 생성된 코드를 Python REPL 도구로 실행하고 결과를 반환합니다.
        """
        logger.debug("--- [Agent Node: CodeExecution Tool] ---")
        tool = self.tools.get("python_repl")
        if not tool:
            logger.warning("코드 실행 도구 미설정 - 'python_repl' 키를 찾을 수 없음")
            return {
                "tool_outputs": {"code_result": "코드 실행 도구가 설정되지 않았습니다."}
            }

        # 1. RAG로 사내 코드 컨텍스트 검색
        logger.debug("CodeExecution: RAG로 사내 코드 컨텍스트 검색 시도...")
        try:
            code_docs = await self.vector_store.search(
                query_embedding=self.vector_store.embedding_model.embed_query(
                    state["question"]
                ),
                allowed_groups=state["permission_groups"],
                k=3,
                doc_ids_filter={"source_type": "github-repo"},
            )
            context_str = (
                "\n\n---\n\n".join([doc["page_content"] for doc in code_docs])
                if code_docs
                else "No internal code context found."
            )
            logger.info("CodeExecution: %d개의 코드 스니펫 주입.", len(code_docs))
        except Exception as e:
            logger.warning("CodeExecution: RAG 컨텍스트 검색 실패: %s", e)
            context_str = "Error fetching code context."

        # 2. 컨텍스트 기반으로 실행할 Python 코드 생성
        code_gen_prompt = prompts.CODE_GEN_PROMPT.format(
            question=state["question"], context=context_str
        )
        response = await self.llm_powerful.invoke(
            [HumanMessage(content=code_gen_prompt)], config={}
        )
        # LLM이 생성한 코드 블록(```python ... ```)에서 순수 코드만 추출합니다.
        code_to_run = (
            response.content.strip().replace("```python", "").replace("```", "")
        )
        logger.info("실행할 코드 생성 완료 - 길이 %d자", len(code_to_run))

        # 3. 생성된 코드 실행
        # `tool.run`은 동기 함수이므로, `asyncio.to_thread`를 사용해 별도 스레드에서 실행하여
        # 이벤트 루프가 블로킹되는 것을 방지합니다.
        code_result = await asyncio.to_thread(tool.run, tool_input=code_to_run)
        logger.debug("코드 실행 결과 수신 - result='%s...'", str(code_result)[:120])

        tool_outputs = state.get("tool_outputs", {})
        tool_outputs["code_result"] = str(code_result)
        return {"tool_outputs": tool_outputs, "code_input": code_to_run}

    async def generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 3: 최종 답변 생성] 이전 노드들에서 수집된 모든 컨텍스트를 종합하여 최종 답변을 생성합니다.

        - 라우터에서 선택된 LLM('fast' 또는 'powerful')을 사용합니다.
        - 도구 실행 결과(RAG, 웹 검색, 코드 실행)를 프롬프트의 컨텍스트로 동적으로 조합합니다.
        - 대화 기록, 사용자 프로필 등 추가 정보를 포함하여 최종 프롬프트를 구성합니다.
        """
        logger.debug("--- [Agent Node: Generate Final Answer] ---")
        llm = (
            self.llm_powerful
            if state.get("chosen_llm") == "powerful"
            else self.llm_fast
        )
        logger.debug(
            "최종 답변 생성 - 선택된 LLM=%s, tool_choice=%s",
            "powerful" if llm is self.llm_powerful else "fast",
            state.get("tool_choice"),
        )

        # 도구 사용 여부와 결과에 따라 LLM에 제공할 컨텍스트 문자열을 동적으로 구성합니다.
        context_str = ""
        tool_choice = state.get("tool_choice")
        tool_outputs = state.get("tool_outputs", {})

        if tool_choice == "RAG" and tool_outputs.get("rag_chunks"):
            for chunk in tool_outputs["rag_chunks"]:
                print(chunk)
            docs = [chunk["chunk_text"] for chunk in tool_outputs["rag_chunks"]]
            context_str = "[사내 RAG 정보]\n" + "\n\n---\n\n".join(docs)
        elif tool_choice == "WebSearch" and tool_outputs.get("search_result"):
            context_str = f"[웹 검색 결과]\n{tool_outputs['search_result']}"
        elif tool_choice == "CodeExecution" and tool_outputs.get("code_result"):
            code_input = state.get("code_input", "")
            code_result = tool_outputs.get("code_result", "")
            context_str = (
                f"[실행된 코드]\n{code_input}\n\n[코드 실행 결과]\n{code_result}"
            )
        elif tool_choice == "DynamicTool" and tool_outputs.get("dynamic_tool_result"):
            tool_name = state.get("dynamic_tool_to_call").name
            tool_result = tool_outputs.get("dynamic_tool_result")
            context_str = f"[실행된 동적 도구: {tool_name}]\n{tool_result}"
        elif tool_choice == "None":
            context_str = (
                "도움말: 일반 대화 모드입니다. RAG, 웹 검색, 코드 실행 없이 답변합니다."
            )
        else:
            context_str = (
                "도움말: 관련 정보를 찾지 못했거나, 선택된 도구의 결과가 없습니다."
            )

        # 최종 프롬프트를 조립합니다.
        hybrid_context = state.get("hybrid_context", "")

        prompt = prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
            hybrid_context=hybrid_context,
            tool_context=context_str,
            question=state["question"],
            permission_groups=state["permission_groups"],
            user_profile=state.get("user_profile", "Not specified"),
        )
        messages = [HumanMessage(content=prompt)]

        # LLM 스트리밍 호출을 통해 최종 답변을 생성합니다.
        full_answer = ""
        async for chunk in llm.stream(messages, config={}):
            full_answer += chunk.content

        return {"answer": full_answer}

    async def output_guardrail(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 4: 출력 가드레일] 생성된 최종 답변을 검증하고, 유해하거나 부적절할 경우 안전한 메시지로 대체합니다.

        이 노드는 에이전트의 마지막 방어선으로, 책임감 있는 AI(Responsible AI)를 위한
        필수적인 단계입니다. 'fast' LLM을 사용하여 빠르게 안전성 여부를 판단합니다.
        """
        logger.debug("--- [Agent Node: Output Guardrail] ---")
        final_answer = state.get("answer", "")
        if not final_answer.strip():
            logger.debug("Guardrail: 빈 답변, 검증 없이 통과.")
            return {"answer": final_answer}

        prompt = prompts.GUARDRAIL_PROMPT_TEMPLATE.format(answer=final_answer)

        try:
            # 타임아웃(3초)을 설정하여 가드레일 검증이 전체 응답 시간을 과도하게 지연시키지 않도록 합니다.
            response = await asyncio.wait_for(
                self.llm_fast.invoke([HumanMessage(content=prompt)], config={}),
                timeout=3.0,
            )
            decision = response.content.strip().upper()

            # LLM의 판단이 'UNSAFE'일 경우, 미리 정의된 안전한 메시지로 답변을 교체합니다.
            if "UNSAFE" in decision:
                logger.warning(
                    "Guardrail: 답변이 UNSAFE로 분류됨. 원본: '%s...'",
                    final_answer[:100],
                )
                safe_answer = "보안 정책에 따라 답변을 수정했습니다. (This response has been modified according to security policies.)"
                return {"answer": safe_answer}

            logger.debug("Guardrail: 답변이 SAFE로 분류됨, 통과.")
            return {"answer": final_answer}

        except Exception as e:
            # 가드레일 실행 중 타임아웃 또는 기타 오류 발생 시, 안전을 위해 답변을 차단하고
            # 오류 메시지를 포함한 안전한 답변으로 대체합니다.
            logger.error("Guardrail: 가드레일 실행 중 오류 발생: %s", e)
            safe_answer = (
                f"답변 생성 중 오류가 발생했습니다. (Error during guardrail check: {e})"
            )
            return {"answer": safe_answer}
