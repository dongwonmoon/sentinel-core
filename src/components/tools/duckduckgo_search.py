# -*- coding: utf-8 -*-
"""
DuckDuckGo 검색 엔진을 사용하여 웹 검색을 수행하는 도구를 제공합니다.
"""

from langchain_community.tools import DuckDuckGoSearchRun

from .base import BaseTool
from ...core.logger import get_logger

logger = get_logger(__name__)


def get_duckduckgo_search_tool() -> BaseTool:
    """
    DuckDuckGo 웹 검색 도구 인스턴스를 생성하여 반환합니다.

    이 함수는 LangChain 커뮤니티에서 제공하는 기성 도구인 `DuckDuckGoSearchRun`을
    래핑(wrapping)하여 사용합니다. 복잡한 웹 스크레이핑이나 API 연동 로직을
    직접 구현할 필요 없이, 검증된 라이브러리 기능을 활용하여 효율적으로
    웹 검색 기능을 에이전트에 통합할 수 있습니다.

    Returns:
        BaseTool: LangChain의 `BaseTool` 인터페이스를 따르는 DuckDuckGo 검색 도구 객체.
                  이 객체는 `name`, `description`, `_run` 메서드 등을 이미 내장하고 있습니다.
    """
    logger.info("DuckDuckGo 검색 도구 초기화를 시작합니다...")
    try:
        # DuckDuckGoSearchRun 인스턴스를 생성합니다.
        # 이 클래스 내부적으로 DuckDuckGo Search API를 호출하는 로직이 구현되어 있습니다.
        tool = DuckDuckGoSearchRun()

        # LangChain 에이전트가 이 도구를 명확하게 식별하고 선택할 수 있도록
        # `name` 속성을 시스템의 명명 규칙에 맞게 커스터마이징합니다.
        # (기본값은 'duckduckgo_search'로 동일하지만, 명시적으로 설정하여 일관성을 유지합니다.)
        tool.name = "duckduckgo_search"

        # `description`은 `DuckDuckGoSearchRun` 클래스에 이미 잘 정의되어 있어
        # LLM이 그 기능을 이해하는 데 충분하므로 별도로 수정하지 않습니다.
        # (기본 설명: "A wrapper around DuckDuckGo Search. Useful for when you need to answer questions about current events. Input should be a search query.")

        logger.info(f"'{tool.name}' 도구 초기화가 완료되었습니다.")
        return tool
    except Exception as e:
        logger.error(
            f"DuckDuckGo 검색 도구 초기화 중 오류 발생: {e}", exc_info=True
        )
        raise
