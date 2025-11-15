# -*- coding: utf-8 -*-
"""
OpenAI 및 OpenAI 호환 API(예: Groq)를 통해 호스팅되는 LLM을 사용하기 위한 구체적인 구현체입니다.
"""

from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from .base import BaseLLM
from ...core.logger import get_logger

logger = get_logger(__name__)


class OpenAILLM(BaseLLM):
    """
    OpenAI 또는 OpenAI 호환 API(Groq 등)를 사용하여 LLM 기능을 수행하는 클래스입니다.

    `BaseLLM` 추상 클래스를 상속받아, `langchain-openai`의 `ChatOpenAI` 클라이언트를 사용하여
    스트리밍 및 호출 로직을 구체적으로 구현합니다.
    """

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str],
        temperature: float = 0.0,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        OpenAILLM 클래스의 인스턴스를 초기화합니다.

        Args:
            model_name (str): 사용할 OpenAI 호환 모델의 이름 (예: "gpt-4o", "llama3-70b-8192").
            api_key (Optional[str]): 인증을 위한 API 키.
            temperature (float): 모델의 생성 온도. 0에 가까울수록 결정적인 답변을 생성합니다.
            base_url (Optional[str]): API 서버의 기본 URL.
                                     OpenAI 공식 API가 아닌 Groq 등 다른 엔드포인트를 사용할 때 필요합니다.
            **kwargs: `ChatOpenAI`에 전달할 추가적인 인자.
        """
        self._model_name = model_name
        self._provider = "openai"

        api_display_name = "OpenAI"
        if base_url:
            # URL에서 도메인 이름을 추출하여 로깅에 사용 (예: 'api.groq.com')
            try:
                api_display_name = base_url.split("://")[1].split("/")[0]
            except IndexError:
                api_display_name = base_url

        logger.info(
            f"{api_display_name} 호환 LLM ('{model_name}') 초기화를 시작합니다."
        )

        if not api_key:
            logger.warning(
                f"'{model_name}' 모델에 대한 API 키가 제공되지 않았습니다. "
                "환경 변수(예: OPENAI_API_KEY)에 설정되어 있는지 확인하세요."
            )

        try:
            # langchain-openai의 ChatOpenAI 클라이언트를 초기화합니다.
            self._client = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
            logger.info(
                f"{api_display_name} 호환 LLM ('{model_name}') 초기화가 완료되었습니다."
            )
        except Exception as e:
            logger.error(
                f"{api_display_name} 호환 LLM ('{model_name}') 초기화 중 오류 발생: {e}",
                exc_info=True,
            )
            raise

    @property
    def client(self) -> Runnable:
        """
        초기화된 `ChatOpenAI` 클라이언트 인스턴스를 반환합니다.
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
        LLM 제공자 이름("openai")을 반환합니다.
        """
        return self._provider

    async def stream(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> AsyncIterator[Any]:
        """
        OpenAI 호환 모델로부터 응답을 스트리밍합니다.
        실제 로직은 `ChatOpenAI`의 `astream` 메서드에 위임합니다.

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
        OpenAI 호환 모델을 호출하여 전체 응답을 한 번에 받습니다.
        실제 로직은 `ChatOpenAI`의 `ainvoke` 메서드에 위임합니다.

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
