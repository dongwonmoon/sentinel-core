# -*- coding: utf-8 -*-
"""
Ollama를 통해 호스팅되는 LLM(Large Language Model)을 사용하기 위한 구체적인 구현체입니다.
"""

from typing import Any, AsyncIterator, Dict, List

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_ollama.chat_models import ChatOllama

from .base import BaseLLM
from ...core.logger import get_logger

logger = get_logger(__name__)


class OllamaLLM(BaseLLM):
    """
    Ollama를 사용하여 LLM 기능을 수행하는 클래스입니다.

    `BaseLLM` 추상 클래스를 상속받아, Ollama 모델에 대한 구체적인
    스트리밍 및 호출 로직을 `langchain-ollama`의 `ChatOllama`를 사용하여 구현합니다.
    """

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.0,
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ):
        """
        OllamaLLM 클래스의 인스턴스를 초기화합니다.

        Args:
            model_name (str): 사용할 Ollama 모델의 이름 (예: "gemma2:9b").
            temperature (float): 모델의 생성 온도. 0에 가까울수록 결정적인 답변을 생성합니다.
            base_url (str): Ollama API 서버의 기본 URL.
            **kwargs: `ChatOllama`에 전달할 추가적인 인자.
        """
        self._model_name = model_name
        self._provider = "ollama"

        logger.info(
            f"Ollama LLM ('{model_name}') 초기화를 시작합니다. (API: {base_url})"
        )
        try:
            # langchain-ollama의 ChatOllama 클라이언트를 초기화합니다.
            self._client = ChatOllama(
                model=model_name,
                temperature=temperature,
                base_url=base_url,
                **kwargs,
            )
            logger.info(f"Ollama LLM ('{model_name}') 초기화가 완료되었습니다.")
        except Exception as e:
            logger.error(
                f"Ollama LLM ('{model_name}') 초기화 중 오류 발생: {e}",
                exc_info=True,
            )
            # 초기화 실패 시, 애플리케이션이 계속 실행될 수 있도록 하되,
            # 이후 호출에서 오류가 발생하도록 처리할 수 있습니다.
            # 여기서는 예외를 다시 발생시켜, 시스템 시작 단계에서 문제를 인지하도록 합니다.
            raise

    @property
    def client(self) -> Runnable:
        """
        초기화된 `ChatOllama` 클라이언트 인스턴스를 반환합니다.
        `BaseLLM`의 추상 속성을 구현합니다.
        """
        return self._client

    @property
    def model_name(self) -> str:
        """
        현재 사용 중인 모델의 이름을 반환합니다.
        """
        return self._model_name

    @property
    def provider(self) -> str:
        """
        LLM 제공자 이름("ollama")을 반환합니다.
        """
        return self._provider

    async def stream(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> AsyncIterator[Any]:
        """
        Ollama 모델로부터 응답을 스트리밍합니다.
        `BaseLLM`의 추상 메서드를 구현하며, 실제 로직은 `ChatOllama`의 `astream` 메서드에 위임합니다.

        Args:
            messages (List[BaseMessage]): LLM에 전달할 메시지 목록.
            config (Dict[str, Any]): LangChain 실행에 필요한 설정.

        Yields:
            AsyncIterator[Any]: LLM이 생성하는 응답 청크(chunk).
        """
        logger.debug(f"'{self.model_name}' 모델로 스트리밍 요청을 시작합니다.")
        async for chunk in self.client.astream(messages, config=config):
            yield chunk
        logger.debug(f"'{self.model_name}' 모델의 스트리밍이 종료되었습니다.")

    async def invoke(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> Any:
        """
        Ollama 모델을 호출하여 전체 응답을 한 번에 받습니다.
        `BaseLLM`의 추상 메서드를 구현하며, 실제 로직은 `ChatOllama`의 `ainvoke` 메서드에 위임합니다.

        Args:
            messages (List[BaseMessage]): LLM에 전달할 메시지 목록.
            config (Dict[str, Any]): LangChain 실행에 필요한 설정.

        Returns:
            Any: LLM의 전체 응답 내용 (`AIMessage` 객체).
        """
        logger.debug(
            f"'{self.model_name}' 모델로 단일 응답(invoke) 요청을 시작합니다."
        )
        response = await self.client.ainvoke(messages, config=config)
        logger.debug(
            f"'{self.model_name}' 모델로부터 단일 응답을 수신했습니다."
        )
        return response
