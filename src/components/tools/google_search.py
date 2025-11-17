from .base import BaseTool
from ...core.config import Settings
from ...core.logger import get_logger

logger = get_logger(__name__)


def get_google_search_tool(settings: Settings) -> BaseTool:
    """
    Google 검색 도구 인스턴스를 생성하여 반환합니다. (현재는 플레이스홀더)

    이 함수는 향후 Google Custom Search Engine (CSE) API를 사용하여
    웹 검색 기능을 구현하기 위한 자리 표시자입니다.
    실제 구현을 위해서는 `GOOGLE_API_KEY`와 `GOOGLE_CSE_ID` 설정이 필요합니다.
    """
    logger.warning(
        "Google 검색 도구가 `get_tools` 팩토리에서 호출되었지만, 아직 구현되지 않았습니다."
    )
    raise NotImplementedError(
        "Google 검색 도구는 아직 구현되지 않았습니다. "
        "구현하려면 이 파일을 수정하고, 필요한 API 키를 설정해야 합니다."
    )
    # 향후 구현 예시:
    # from langchain_google_community import GoogleSearchAPIWrapper
    # from langchain.tools import Tool
    #
    # if not settings.GOOGLE_API_KEY or not settings.GOOGLE_CSE_ID:
    #     logger.error("Google 검색을 위한 API 키 또는 CSE ID가 설정되지 않았습니다.")
    #     return None # 또는 예외 발생
    #
    # search = GoogleSearchAPIWrapper(
    #     google_api_key=settings.GOOGLE_API_KEY,
    #     google_cse_id=settings.GOOGLE_CSE_ID
    # )
    # return Tool(
    #     name="google_search",
    #     description="최신 정보를 얻기 위해 Google을 사용하여 웹을 검색합니다.",
    #     func=search.run,
    # )
