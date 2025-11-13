from .base import BaseTool
from ..config import Settings
from ..logger import get_logger

logger = get_logger(__name__)


def get_google_search_tool(settings: Settings) -> BaseTool:
    """
    Google 검색 도구 인스턴스를 생성하여 반환합니다. (플레이스홀더)
    """
    logger.warning(
        "Google 검색 도구가 초기화되었지만, 아직 구현되지 않았습니다."
    )
    raise NotImplementedError("Google 검색 도구는 아직 구현되지 않았습니다.")
    # 향후 구현 예시:
    # from langchain_google_community import GoogleSearchAPIWrapper
    # from langchain.tools import Tool
    # search = GoogleSearchAPIWrapper(
    #     google_api_key=settings.GOOGLE_API_KEY,
    #     google_cse_id=settings.GOOGLE_CSE_ID
    # )
    # return Tool(
    #     name="google_search",
    #     description="최신 정보를 얻기 위해 웹을 검색합니다.",
    #     func=search.run,
    # )
