# -*- coding: utf-8 -*-
"""
LLM(Large Language Model) 컴포넌트의 기본 인터페이스를 정의하는 모듈입니다.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable


class BaseLLM(ABC):
    """
    생성형 LLM(Large Language Model)의 기본 인터페이스를 정의하는 추상 기본 클래스(Abstract Base Class)입니다.

    이 클래스는 시스템 내에서 사용되는 모든 구체적인 LLM 클래스(예: `OllamaLLM`, `OpenAILLM`)들이
    반드시 구현해야 하는 공통적인 메서드와 속성을 강제합니다.
    이를 통해, 어떤 LLM을 사용하든 동일한 방식으로 호출하고 제어할 수 있어
    LLM 교체의 유연성을 확보하고 코드의 일관성을 유지할 수 있습니다.
    """

    @property
    @abstractmethod
    def client(self) -> Runnable:
        """
        LangChain의 `Runnable` 인터페이스를 준수하는 LLM 클라이언트 객체를 반환해야 합니다.

        `Runnable`은 LangChain Expression Language (LCEL)의 핵심 요소로,
        `.stream()`, `.invoke()`, `.batch()` 등의 메서드를 통해 LLM 호출을 표준화합니다.
        이 속성을 통해 반환된 객체는 LangChain의 다른 컴포넌트와 원활하게 연동됩니다.

        Returns:
            Runnable: LangChain 호환 LLM 클라이언트 객체.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        현재 사용 중인 LLM의 모델 이름을 문자열로 반환해야 합니다.
        (예: "gemma2:9b", "gpt-4o")

        Returns:
            str: LLM 모델 이름.
        """
        pass

    @property
    @abstractmethod
    def provider(self) -> str:
        """
        현재 LLM의 제공자(Provider)를 문자열로 반환해야 합니다.
        (예: "ollama", "openai")

        Returns:
            str: LLM 제공자 이름.
        """
        pass

    @abstractmethod
    async def stream(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> AsyncIterator[Any]:
        """
        주어진 메시지 목록을 바탕으로 LLM의 응답을 스트리밍(Streaming) 방식으로 반환합니다.

        이 메서드는 챗봇처럼 답변이 생성되는 과정을 실시간으로 보여줘야 할 때 사용됩니다.
        LLM이 생성하는 텍스트 조각(토큰)들을 비동기 제너레이터(Async Generator)를 통해
        하나씩 `yield`합니다.

        Args:
            messages (List[BaseMessage]): LLM에 전달할 메시지 목록.
                                           (예: `[SystemMessage(...), HumanMessage(...)]`)
            config (Dict[str, Any]): LangChain 실행에 필요한 추가 설정.
                                     (예: `{"callbacks": [...]}`)

        Returns:
            AsyncIterator[Any]: 응답 청크(chunk)를 비동기적으로 반환하는 이터레이터.
        """
        pass

    @abstractmethod
    async def invoke(self, messages: List[BaseMessage], config: Dict[str, Any]) -> Any:
        """
        주어진 메시지 목록을 바탕으로 LLM의 전체 응답을 한 번에 반환합니다.

        스트리밍이 필요 없는 내부적인 처리나 단일 응답이 필요할 때 사용됩니다.

        Args:
            messages (List[BaseMessage]): LLM에 전달할 메시지 목록.
            config (Dict[str, Any]): LangChain 실행에 필요한 추가 설정.

        Returns:
            Any: LLM의 전체 응답 내용 (일반적으로 `AIMessage` 객체).
        """
        pass
