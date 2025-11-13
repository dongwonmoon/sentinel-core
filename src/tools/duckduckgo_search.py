from langchain_community.tools import DuckDuckGoSearchRun
from .base import BaseTool
from ..logger import get_logger

logger = get_logger(__name__)

def get_duckduckgo_search_tool() -> BaseTool:
    """
    DuckDuckGo 검색 도구 인스턴스를 생성하여 반환합니다.

    Returns:
        LangChain의 BaseTool 인터페이스를 따르는 DuckDuckGo 검색 도구 객체.
    """
    logger.info("DuckDuckGo 검색 도구 초기화 완료.")
    return DuckDuckGoSearchRun()
