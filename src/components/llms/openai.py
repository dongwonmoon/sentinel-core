from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from .base import BaseLLM
from ...core.config import Settings


class OpenAILLM(BaseLLM):
    """
    OpenAI 호환 API(Groq 등)를 사용하여 LLM 기능을 수행하는 클래스입니다.
    """

    _client: Runnable

    def __init__(
        self,
        base_url: Optional[str],
        model_name: str,
        api_key: Optional[str],
        temperature: float = 0,
    ):
        """
        Groq/OpenAI LLM 클라이언트를 초기화합니다.
        """
        self._client = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
        )
        print(f"INFO: OpenAI/Groq LLM 초기화 완료. 모델: {model_name}")

    @property
    def client(self) -> Runnable:
        return self._client

    async def stream(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> AsyncIterator[Any]:
        async for chunk in self.client.astream(messages, config=config):
            yield chunk

    async def invoke(
        self, messages: List[BaseMessage], config: Dict[str, Any]
    ) -> Any:
        return await self.client.ainvoke(messages, config=config)
