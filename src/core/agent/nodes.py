"""Agent의 각 노드(Node)에 대한 실제 실행 로직을 정의합니다."""

import asyncio
from typing import List, Dict, Any

from langchain_core.messages import HumanMessage

from .state import AgentState, convert_history_dicts_to_messages
from .. import prompts
from ...components.llms.base import BaseLLM
from ...components.rerankers.base import BaseReranker
from ...components.tools.base import BaseTool
from ...components.vector_stores.base import BaseVectorStore
from ..logger import get_logger

logger = get_logger(__name__)


class AgentNodes:
    """Agent의 각 노드에 대한 실행 로직을 담고 있는 클래스입니다."""

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

    async def route_query(self, state: AgentState) -> Dict[str, Any]:
        """
        [노드] LLM을 이용해 질문을 분석하고 사용할 도구를 결정합니다.
        """
        logger.debug("--- [Agent Node: Route Query] ---")
        question = state["question"]
        history = convert_history_dicts_to_messages(state.get("chat_history", []))
        logger.debug(
            "라우터 입력 - history=%d개, doc_filter=%s",
            len(history),
            state.get("doc_ids_filter"),
        )
        prompt = prompts.ROUTER_PROMPT_TEMPLATE.format(
            history="\n".join([f"{m.type}: {m.content}" for m in history]),
            question=question,
            failed_tools=state.get("failed_tools", []),
        )

        response = await self.llm_fast.invoke([HumanMessage(content=prompt)], config={})

        try:
            decision_text = response.content.strip().replace("[", "").replace("]", "")
            llm_part, tool_part = [part.strip() for part in decision_text.split(",")]
            chosen_llm = "powerful" if "powerful" in llm_part.lower() else "fast"
            tool_choice = (
                tool_part
                if tool_part in ["RAG", "WebSearch", "CodeExecution", "None"]
                else "None"
            )
        except Exception as e:
            logger.warning(f"라우터 출력 파싱 실패 ({e}). [fast, None]으로 Fallback.")
            chosen_llm, tool_choice = "fast", "None"

        logger.info(f"라우터 결정 -> LLM: {chosen_llm}, 도구: {tool_choice}")
        return {
            "chosen_llm": chosen_llm,
            "tool_choice": tool_choice,
            "tool_outputs": {},
        }

    async def run_rag_tool(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 'RAG' 도구를 실행합니다 (Retrieve -> Rerank)."""
        logger.debug("--- [Agent Node: RAG Tool] ---")
        retrieved = await self.vector_store.search(
            query=state["question"],
            allowed_groups=state["permission_groups"],
            k=10,
            doc_ids_filter=state.get("doc_ids_filter"),
        )
        if not retrieved:
            logger.info("RAG 검색 결과 없음 - 질문='%s'", state["question"][:80])
            failed = state.get("failed_tools", [])
            failed.append("RAG")
            return {"tool_outputs": {"rag_chunks": []}, "failed_tools": failed}

        reranked = self.reranker.rerank(state["question"], retrieved)
        final_docs = reranked[: state["top_k"]]
        logger.info(
            "RAG 검색 완료 - 원본 %d건, 리랭크 후 %d건",
            len(retrieved),
            len(final_docs),
        )

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
        """[노드] 'WebSearch' 도구를 실행합니다."""
        logger.debug("--- [Agent Node: WebSearch Tool] ---")
        tool = self.tools.get("duckduckgo_search")
        if not tool:
            logger.warning("웹 검색 도구 미설정 - duckduckgo_search 키를 찾을 수 없음")
            return {
                "tool_outputs": {"search_result": "웹 검색 도구가 설정되지 않았습니다."}
            }

        result = await tool.arun(tool_input=state["question"])
        return {"tool_outputs": {"search_result": result}}

    async def run_code_execution_tool(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 'CodeExecution' 도구를 실행합니다."""
        logger.debug("--- [Agent Node: CodeExecution Tool] ---")
        tool = self.tools.get("python_repl")
        if not tool:
            logger.warning("코드 실행 도구 미설정 - python_repl 키를 찾을 수 없음")
            return {
                "tool_outputs": {"code_result": "코드 실행 도구가 설정되지 않았습니다."}
            }

        logger.debug("CodeExecution: RAG로 사내 코드 컨텍스트 검색 시도...")
        try:
            code_docs, _ = await asyncio.wait_for(
                self.vector_store.search(
                    query=state["question"],
                    allowed_groups=state["permission_groups"],
                    k=3,  # 관련성 높은 코드 3개
                    source_type_filter="github-repo",  # 2단계에서 구현한 필터 사용
                ),
                timeout=5.0,
            )

            if code_docs:
                context_str = "\n\n---\n\n".join(
                    [doc.page_content for doc, score in code_docs]
                )
                logger.info(
                    "CodeExecution: %d개의 코드 스니펫을 컨텍스트로 주입.",
                    len(code_docs),
                )
            else:
                context_str = "No internal code context found."

        except Exception as e:
            logger.warning("CodeExecution: RAG 컨텍스트 검색 실패: %s", e)
            context_str = "Error fetching code context."

        code_gen_prompt = prompts.CODE_GEN_PROMPT.format(
            question=state["question"], context=context_str
        )
        response = await self.llm_powerful.invoke(
            [HumanMessage(content=code_gen_prompt)], config={}
        )
        code_to_run = (
            response.content.strip().replace("```python", "").replace("```", "")
        )
        logger.info("코드 실행 프롬프트 생성 완료 - 길이 %d자", len(code_to_run))

        code_result = await asyncio.to_thread(tool.run, tool_input=code_to_run)
        logger.debug("코드 실행 결과 수신 - result='%s...'", str(code_result)[:120])

        tool_outputs = state.get("tool_outputs", {})
        tool_outputs["code_result"] = str(code_result)
        return {"tool_outputs": tool_outputs, "code_input": code_to_run}

    async def generate_final_answer(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 모든 컨텍스트를 종합하여 최종 답변을 생성합니다."""
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

        context_str = ""
        tool_choice = state.get("tool_choice")
        tool_outputs = state.get("tool_outputs", {})

        if tool_choice == "RAG" and tool_outputs.get("rag_chunks"):
            docs = [chunk["page_content"] for chunk in tool_outputs["rag_chunks"]]
            context_str = "[사내 RAG 정보]\n" + "\n\n---\n\n".join(docs)
        elif tool_choice == "WebSearch" and tool_outputs.get("search_result"):
            context_str = f"[웹 검색 결과]\n{tool_outputs['search_result']}"
        elif tool_choice == "CodeExecution" and tool_outputs.get("code_result"):
            code_input = state.get("code_input", "")
            code_result = tool_outputs.get("code_result", "")
            context_str = (
                f"[실행된 코드]\n{code_input}\n\n[코드 실행 결과]\n{code_result}"
            )
        elif tool_choice == "None":
            context_str = (
                "도움말: 일반 대화 모드입니다. RAG, 웹 검색, 코드 실행 없이 답변합니다."
            )
        else:
            context_str = (
                "도움말: 관련 정보를 찾지 못했거나, 선택된 도구의 결과가 없습니다."
            )

        history = convert_history_dicts_to_messages(state.get("chat_history", []))
        prompt = prompts.FINAL_ANSWER_PROMPT_TEMPLATE.format(
            context=context_str,
            question=state["question"],
            permission_groups=state["permission_groups"],
            user_profile=state.get("user_profile", "Not specified"),
        )
        messages = history + [HumanMessage(content=prompt)]

        full_answer = ""
        async for chunk in llm.stream(messages, config={}):
            full_answer += chunk.content

        return {"answer": full_answer}

    async def output_guardrail(self, state: AgentState) -> Dict[str, Any]:
        """[노드] 최종 답변을 검증하고, 위험할 경우 안전한 메시지로 대체합니다."""
        logger.debug("--- [Agent Node: Output Guardrail] ---")
        final_answer = state.get("answer", "")
        if not final_answer.strip():
            logger.debug("Guardrail: 빈 답변, 통과.")
            return {"answer": final_answer}

        prompt = prompts.GUARDRAIL_PROMPT_TEMPLATE.format(answer=final_answer)

        try:
            response = await asyncio.wait_for(
                self.llm_fast.invoke([HumanMessage(content=prompt)], config={}),
                timeout=3.0,  # 가드레일은 3초 이내에 응답해야 함
            )
            decision = response.content.strip().upper()

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
            logger.error("Guardrail: 가드레일 실행 중 오류 발생: %s", e)
            # 안전을 위해 가드레일 실패 시에도 답변을 차단
            safe_answer = (
                f"답변 생성 중 오류가 발생했습니다. (Error during guardrail check: {e})"
            )
            return {"answer": safe_answer}
