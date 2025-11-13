from typing import Any, AsyncIterator, Dict, List

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_ollama.chat_models import ChatOllama

from .base import BaseLLM
from ..config import Settings
from ..logger import get_logger

logger = get_logger(__name__)


class OllamaLLM(BaseLLM):
    """
    Ollama를 사용하여 LLM 기능을 수행하는 클래스입니다.
    BaseLLM을 상속받아 구체적인 스트리밍 및 호출 로직을 구현합니다.
    """

    _client: Runnable

    def __init__(self, base_url: str, model_name: str, temperature: float = 0):
        """
        OllamaLLM 클래스의 인스턴스를 초기화합니다.

        Args:
            settings: 애플리케이션의 설정을 담고 있는 Settings 객체입니다.
        """
        self._client = ChatOllama(
            base_url=base_url,
            model=model_name,
            temperature=temperature,
        )
        logger.info(f"Ollama LLM 초기화 완료. 모델: {model_name}")

    @property
    def client(self) -> Runnable:
        """
        초기화된 ChatOllama 클라이언트 인스턴스를 반환합니다.
        """
        return self._client

    async def stream(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> AsyncIterator[Any]:
        """
        Ollama 모델로부터 응답을 스트리밍합니다.

        Args:
            messages: LLM에 전달할 메시지 목록입니다.
            config: LangChain 실행에 필요한 설정입니다.

        Returns:
            응답 청크를 비동기적으로 반환하는 이터레이터입니다.
        """
        async for chunk in self.client.astream(messages, config=config):
            yield chunk

    async def invoke(self, messages: List[BaseMessage], config: Dict[str, Any]) -> Any:
        """
        Ollama 모델을 호출하여 전체 응답을 받습니다.

        Args:
            messages: LLM에 전달할 메시지 목록입니다.
            config: LangChain 실행에 필요한 설정입니다.

        Returns:
            LLM의 전체 응답 내용입니다.
        """
        return await self.client.ainvoke(messages, config=config)
