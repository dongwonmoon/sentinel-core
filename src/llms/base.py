from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

class BaseLLM(ABC):
    """
    생성용 LLM (Large Language Model)의 기본 인터페이스를 정의하는 추상 기본 클래스입니다.
    모든 구체적인 LLM 클래스는 이 클래스를 상속받아야 합니다.
    """

    @property
    @abstractmethod
    def client(self) -> Runnable:
        """
        LangChain Runnable 인터페이스를 준수하는 LLM 클라이언트 객체를 반환해야 합니다.
        """
        pass

    @abstractmethod
    async def stream(self, messages: List[BaseMessage], config: Dict[str, Any]) -> AsyncIterator[Any]:
        """
        주어진 메시지를 바탕으로 LLM의 응답을 스트리밍 방식으로 반환합니다.

        Args:
            messages: LLM에 전달할 메시지 목록입니다.
            config: LangChain 실행에 필요한 설정입니다.

        Returns:
            응답 청크(chunk)를 비동기적으로 반환하는 이터레이터입니다.
        """
        pass

    @abstractmethod
    async def invoke(self, messages: List[BaseMessage], config: Dict[str, Any]) -> Any:
        """
        주어진 메시지를 바탕으로 LLM의 전체 응답을 한 번에 반환합니다.

        Args:
            messages: LLM에 전달할 메시지 목록입니다.
            config: LangChain 실행에 필요한 설정입니다.

        Returns:
            LLM의 전체 응답 내용입니다.
        """
        pass
