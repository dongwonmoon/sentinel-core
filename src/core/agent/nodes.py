"""
Agent의 각 노드(Node)에 대한 실제 실행 로직을 정의합니다.

이 파일의 `AgentNodes` 클래스는 LangGraph 워크플로우의 각 단계를 구성하는
메서드들을 포함합니다. 각 메서드는 `AgentState`를 입력으로 받아 특정 작업을
수행하고, 상태를 업데이트하는 딕셔너리를 반환합니다.
"""

import asyncio
from typing import Any, Dict, List
from sqlalchemy import select, text
import httpx
import json

from langchain_core.messages import HumanMessage
from langchain_core.utils.pydantic import PydanticBaseModel

from .. import prompts
from ...components.llms.base import BaseLLM
from ...components.rerankers.base import BaseReranker
from ...components.tools.base import BaseTool
from ...components.vector_stores.base import BaseVectorStore
from ...db import models
from ..logger import get_logger
from .state import AgentState, convert_history_dicts_to_messages, DynamicTool

logger = get_logger(__name__)

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
        self.llm_fast = fast_llm
        self.llm_powerful = powerful_llm
        self.vector_store = vector_store
        self.reranker = reranker
        self.tools = tools

        self.AsyncSessionLocal = getattr(
            vector_store, "AsyncSessionLocal", None
        )
        if not self.AsyncSessionLocal:
            logger.warning("AgentNodes: DB 세션 팩토리를 찾을 수 없습니다.")

    async def build_hybrid_context(self, state: AgentState) -> Dict[str, Any]:
        """
        LangGraph의 새 진입점(Entrypoint).
        3가지 유형의 메모리를 병렬로 인출하여 하이브리드 컨텍스트를 구축합니다.
        A. 최근 대화 (Short-Term)
        B. 대화 요약 (Narrative)
        C. '역사적 RAG' (Long-Term)
        """
        logger.debug("--- [Agent Node: Build Hybrid Context] ---")

        async def get_short_term_memory() -> str:
            """A. 최근 3개의 대화만 원본 그대로 가져옵니다."""
            try:
                # AgentState에 있는 전체 히스토리 사용
                # 3개 하드 코딩. 일단 보류
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
            """B. 전체 대화의 맥락을 요약합니다."""
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
                logger.debug(f"하이브리드 컨텍스트(B): 대화 요약 생성 완료.")
                return f"[대화 요약]\n{summary}"
            except Exception as e:
                logger.warning(f"하이브리드 컨텍스트(B) 요약 실패: {e}")
                return ""

        async def get_long_term_memory() -> str:
            """C. 현재 질문과 관련성이 높은 '과거의 특정 대화'를 RAG로 인출합니다."""
            if not self.AsyncSessionLocal:
                return ""  # DB 세션 없이는 실행 불가
            try:
                # 1. 현재 질문 임베딩
                query_embedding = self.vector_store.embedding_model.embed_query(
                    state["question"]
                )
                query_vec_str = str(query_embedding)

                # 2. 'chat_turn_memory' 테이블 검색
                # LIMIT 하드 코딩. 일단 보류
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
                            "query_embedding": query_vec_str,
                            "session_id": state["session_id"],
                            "user_id": int(state["user_id"]),
                        },
                    )
                    # 임계값 하드 코딩. 일단 보류
                    relevant_turns = [
                        row.turn_text for row in result if row.distance < 0.8
                    ]  # (임계값 0.8)

                if not relevant_turns:
                    logger.debug(
                        "하이브리드 컨텍스트(C): 관련 '사건 기억' 없음."
                    )
                    return ""

                logger.debug(
                    f"하이브리드 컨텍스트(C): 관련 '사건 기억' {len(relevant_turns)}개 인출."
                )
                return f"[관련 과거 기억 (RAG)]\n" + "\n---\n".join(
                    relevant_turns
                )

            except Exception as e:
                logger.warning(
                    f"하이브리드 컨텍스트(C) 인출 실패: {e}", exc_info=True
                )
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

                logger.debug(
                    f"하이브리드 컨텍스트(D): 동적 도구 {len(tools)}개 로드."
                )
                return tools
            except Exception as e:
                logger.warning(
                    f"하이브리드 컨텍스트(D) 도구 로드 실패: {e}", exc_info=True
                )
                return []

        # [실행] 3가지 메모리 인출을 병렬로 실행 + 1가지 도구 목록
        results = await asyncio.gather(
            get_short_term_memory(),
            get_narrative_memory(),
            get_long_term_memory(),
            get_available_dynamic_tools(),
        )

        # 3가지 결과를 하나의 컨텍스트 문자열로 조합
        final_hybrid_context = "\n\n".join(
            filter(None, results)
        )  # 비어있지 않은 결과만 합침
        available_dynamic_tools = results[-1]

        if not final_hybrid_context:
            logger.debug(
                "하이브리드 컨텍스트: 생성된 컨텍스트가 없습니다. (첫 대화일 수 있음)"
            )
            final_hybrid_context = "도움말: 첫 대화입니다."

        return {
            "hybrid_context": final_hybrid_context,
            "available_dynamic_tools": available_dynamic_tools,
        }

    async def route_query(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 1: 라우터] LLM을 이용해 사용자의 질문을 분석하고, 가장 적절한 도구를 결정합니다.

        이 노드는 에이전트의 "두뇌" 역할을 하여, 질문의 의도를 파악하고
        다음에 어떤 작업을 수행할지 결정하는 분기점입니다.
        'fast' LLM을 사용하여 응답 시간을 최소화합니다.

        Args:
            state (AgentState): 현재 에이전트의 상태. 'question', 'chat_history' 등을 포함.

        Returns:
            Dict[str, Any]: 'chosen_llm'과 'tool_choice'를 포함하여 업데이트할 상태 딕셔너리.
        """
        logger.debug("--- [Agent Node: Route Query] ---")
        question = state["question"]
        context = state["hybrid_context"]

        static_tools_desc = []
        if "duckduckgo_search" in self.tools:
            static_tools_desc.append(
                "- WebSearch: 최신 뉴스, 외부 사실 검색. [RAG로 답을 못 찾을 때 사용]"
            )
        if "python_repl" in self.tools:
            static_tools_desc.append(
                "- CodeExecution: Python 코드 실행. [계산, 데이터 분석, RAG 컨텍스트 조작 시 사용]"
            )

        dynamic_tools = state.get("available_dynamic_tools", [])
        dynamic_tools_desc = [tool.to_tool_string() for tool in dynamic_tools]

        dynamic_tool_names = [tool.name for tool in dynamic_tools]
        dynamic_tool_format_instruction = ""
        if dynamic_tools:
            dynamic_tool_format_instruction = (
                f"\n[IMPORTANT] '{dynamic_tool_names}' 중 하나를 선택한 경우,"
                "반드시 다음 JSON 포맷으로 인자(argument)를 함께 출력해야 합니다:\n"
                '{"tool": "선택한_도구_이름", "args": {"인자1": "값1", "인자2": "값2"}}'
            )

        logger.debug(
            "라우터 입력 - doc_filter=%s",
            state.get("doc_ids_filter"),
        )

        # 라우팅 결정을 위한 프롬프트를 생성합니다.
        # 대화 기록, 질문, 이전에 실패한 도구 목록을 컨텍스트로 제공합니다.
        prompt = prompts.ROUTER_PROMPT_TEMPLATE.format(
            context=context,
            static_tools="\n".join(static_tools_desc),
            dynamic_tools="\n".join(dynamic_tools_desc),
            dynamic_tool_format=dynamic_tool_format_instruction,
            question=question,
            failed_tools=state.get("failed_tools", []),
        )

        # 'fast' LLM을 호출하여 신속하게 도구를 결정합니다.
        response = await self.llm_fast.invoke(
            [HumanMessage(content=prompt)], config={}
        )
        response_content = response.content.strip()

        try:
            if response_content.startswith("{"):  # json 확인
                logger.debug("라우터 응답이 JSON(동적 도구) 포맷입니다.")
                tool_call_data = json.loads(response_content)
                tool_name = tool_call_data.get("tool")
                tool_args = tool_call_data.get("args")

                # 실제 사용 가능한 tool인지
                tool_to_call = next(
                    (t for t in dynamic_tools if t.name == tool_name)
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
                        f"LLM이 유효하지 않은 동적 도구 ({tool_name})를 선택했습니다)"
                    )
                    raise ValueError("Invalid dynamic tool call")

            # 기존 정적 도구 포맷인지 확인 ([LLM, TOOL])
            logger.debug("라우터 응답이 정적 도구 포맷입니다.")
            decision_text = response_content.replace("[", "").replace("]", "")
            llm_part, tool_part = [
                part.strip() for part in decision_text.split(",")
            ]

            chosen_llm = (
                "powerful" if "powerful" in llm_part.lower() else "fast"
            )
            tool_choice = (
                tool_part
                if tool_part in ["RAG", "WebSearch", "CodeExecution", "None"]
                else "None"
            )

            logger.info(
                f"라우터 결정 -> LLM: {chosen_llm}, 정적 도구: {tool_choice}"
            )
            return {
                "chosen_llm": chosen_llm,
                "tool_choice": tool_choice,
                "tool_outputs": {},
            }

        except Exception as e:
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
        'DynamicTool'로 라우팅되었을 때,
        `state`에 저장된 도구 정보(엔드포인트, 인자)를 기반으로
        HTTP POST 요청을 실행하고 결과를 반환합니다.
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
            # LLM이 이해할 수 있도록 JSON 문자열로 변환
            result_str = json.dumps(result_data)

            logger.info(
                f"동적 도구 '{tool_name}' 실행 성공. 결과(일부): {result_str[:200]}..."
            )
            return {"tool_outputs": {"dynamic_tool_result": result_str}}

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"동적 도구 '{tool_name}' API 호출 실패 (HTTP {e.response.status_code}): {e.response.text}"
            )
            return {
                "tool_outputs": {
                    "dynamic_tool_result": f"Error: API call failed with status {e.response.status_code}. Details: {e.response.text}"
                }
            }
        except Exception as e:
            logger.error(
                f"동적 도구 '{tool_name}' 실행 중 예기치 않은 오류: {e}",
                exc_info=True,
            )
            return {
                "tool_outputs": {
                    "dynamic_tool_result": f"Error: An unexpected error occurred: {e}"
                }
            }

    async def run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-A: RAG] 'RAG'(Retrieval-Augmented Generation) 도구를 실행합니다.
        벡터 저장소에서 관련 문서를 검색(Retrieve)하고, 리랭커로 순위를 재조정(Rerank)합니다.

        Returns:
            Dict[str, Any]: 검색 및 리랭킹된 문서('rag_chunks')를 포함한 상태 딕셔너리.
                           실패 시 'failed_tools'에 'RAG'를 추가하여 반환합니다.
        """
        logger.debug("--- [Agent Node: RAG Tool] ---")
        # 1. Retrieve: 벡터 저장소에서 문서를 검색합니다.
        # 사용자의 권한 그룹(permission_groups)과 문서 필터(doc_ids_filter)를 고려하여
        # 접근 제어와 필터링을 수행합니다.
        retrieved = await self.vector_store.search(
            query=state["question"],
            allowed_groups=state["permission_groups"],
            k=10,  # 리랭킹의 효율을 위해 충분히 많은 수(10개)를 우선 검색합니다.
            doc_ids_filter=state.get("doc_ids_filter"),
        )

        # 검색 결과가 없으면, 'failed_tools' 상태에 'RAG'를 추가하고 종료합니다.
        # 이 상태는 그래프의 조건부 엣지에서 재시도(retry) 로직을 트리거하는 데 사용됩니다.
        if not retrieved:
            logger.info(
                "RAG 검색 결과 없음 - 질문='%s'", state["question"][:80]
            )
            failed = state.get("failed_tools", [])
            failed.append("RAG")
            return {"tool_outputs": {"rag_chunks": []}, "failed_tools": failed}

        # 2. Rerank: 검색된 문서를 리랭커를 사용해 질문과의 관련도 순으로 재정렬합니다.
        reranked = self.reranker.rerank(state["question"], retrieved)
        # 최종적으로 LLM에 전달할 상위 K개의 문서를 선택합니다.
        final_docs = reranked[: state["top_k"]]
        logger.info(
            "RAG 검색 완료 - 원본 %d건, 리랭크 후 %d건",
            len(retrieved),
            len(final_docs),
        )

        # 다음 노드에서 사용할 수 있도록 문서 내용을 딕셔너리 리스트로 변환하여 상태에 추가합니다.
        dict_docs = [
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in final_docs
        ]
        return {"tool_outputs": {"rag_chunks": dict_docs}}

    async def run_web_search_tool(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 2-B: 웹 검색] 'WebSearch' 도구(DuckDuckGo)를 실행하여 웹 검색을 수행합니다.
        """
        logger.debug("--- [Agent Node: WebSearch Tool] ---")
        tool = self.tools.get("duckduckgo_search")
        if not tool:
            logger.warning(
                "웹 검색 도구 미설정 - duckduckgo_search 키를 찾을 수 없음"
            )
            return {
                "tool_outputs": {
                    "search_result": "웹 검색 도구가 설정되지 않았습니다."
                }
            }

        result = await tool.arun(tool_input=state["question"])
        return {"tool_outputs": {"search_result": result}}

    async def run_code_execution_tool(
        self, state: AgentState
    ) -> Dict[str, Any]:
        """
        [노드 2-C: 코드 실행] 'CodeExecution' 도구를 실행합니다.
        - 1단계: RAG를 통해 질문과 관련된 내부 코드 컨텍스트를 검색합니다.
        - 2단계: 'powerful' LLM을 사용하여 컨텍스트 기반으로 실행할 코드를 생성합니다.
        - 3단계: 생성된 코드를 Python REPL 도구로 실행하고 결과를 반환합니다.
        """
        logger.debug("--- [Agent Node: CodeExecution Tool] ---")
        tool = self.tools.get("python_repl")
        if not tool:
            logger.warning(
                "코드 실행 도구 미설정 - python_repl 키를 찾을 수 없음"
            )
            return {
                "tool_outputs": {
                    "code_result": "코드 실행 도구가 설정되지 않았습니다."
                }
            }

        # 1. RAG로 사내 코드 컨텍스트 검색 (선택적 단계)
        logger.debug("CodeExecution: RAG로 사내 코드 컨텍스트 검색 시도...")
        try:
            # 'github-repo' 소스 타입으로 필터링하여 코드베이스 내의 관련 코드만 검색합니다.
            code_docs, _ = await asyncio.wait_for(
                self.vector_store.search(
                    query=state["question"],
                    allowed_groups=state["permission_groups"],
                    k=3,  # 가장 관련성 높은 코드 3개
                    source_type_filter="github-repo",
                ),
                timeout=5.0,  # 컨텍스트 검색이 너무 오래 걸리지 않도록 타임아웃 설정
            )
            context_str = (
                "\n\n---\n\n".join(
                    [doc.page_content for doc, score in code_docs]
                )
                if code_docs
                else "No internal code context found."
            )
            logger.info(
                "CodeExecution: %d개의 코드 스니펫 주입.", len(code_docs)
            )
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
        logger.info(
            "코드 실행 프롬프트 생성 완료 - 길이 %d자", len(code_to_run)
        )

        # 3. 생성된 코드 실행
        # `tool.run`은 동기 함수이므로, `asyncio.to_thread`를 사용해 별도 스레드에서 실행하여
        # 이벤트 루프가 블로킹되는 것을 방지합니다.
        code_result = await asyncio.to_thread(tool.run, tool_input=code_to_run)
        logger.debug(
            "코드 실행 결과 수신 - result='%s...'", str(code_result)[:120]
        )

        tool_outputs = state.get("tool_outputs", {})
        tool_outputs["code_result"] = str(code_result)
        return {"tool_outputs": tool_outputs, "code_input": code_to_run}

    async def generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 3: 최종 답변 생성] 이전 노드들에서 수집된 모든 컨텍스트를 종합하여 최종 답변을 생성합니다.

        - 라우터에서 선택된 LLM('fast' 또는 'powerful')을 사용합니다.
        - 도구 실행 결과(RAG, 웹 검색, 코드 실행)를 프롬프트의 컨텍스트로 조합합니다.
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
            docs = [
                chunk["page_content"] for chunk in tool_outputs["rag_chunks"]
            ]
            context_str = "[사내 RAG 정보]\n" + "\n\n---\n\n".join(docs)
        elif tool_choice == "WebSearch" and tool_outputs.get("search_result"):
            context_str = f"[웹 검색 결과]\n{tool_outputs['search_result']}"
        elif tool_choice == "CodeExecution" and tool_outputs.get("code_result"):
            code_input = state.get("code_input", "")
            code_result = tool_outputs.get("code_result", "")
            context_str = f"[실행된 코드]\n{code_input}\n\n[코드 실행 결과]\n{code_result}"
        elif tool_choice == "DynamicTool" and tool_outputs.get(
            "dynamic_tool_result"
        ):
            tool_name = state.get("dynamic_tool_to_call").name
            tool_result = tool_outputs.get("dynamic_tool_result")
            context_str = f"[실행된 동적 도구: {tool_name}]\n{tool_result}"
        elif tool_choice == "None":
            context_str = "도움말: 일반 대화 모드입니다. RAG, 웹 검색, 코드 실행 없이 답변합니다."
        else:
            context_str = "도움말: 관련 정보를 찾지 못했거나, 선택된 도구의 결과가 없습니다."

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
        # 이 스트림은 서비스 계층에서 클라이언트로 직접 전달됩니다.
        full_answer = ""
        async for chunk in llm.stream(messages, config={}):
            full_answer += chunk.content

        return {"answer": full_answer}

    async def output_guardrail(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드 4: 출력 가드레일] 생성된 최종 답변을 검증하고, 유해하거나 부적절할 경우 안전한 메시지로 대체합니다.

        이 노드는 에이전트의 마지막 방어선으로, 책임감 있는 AI(Responsible AI)를 위한
        중요한 단계입니다. 'fast' LLM을 사용하여 빠르게 안전성 여부를 판단합니다.
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
            safe_answer = f"답변 생성 중 오류가 발생했습니다. (Error during guardrail check: {e})"
            return {"answer": safe_answer}
