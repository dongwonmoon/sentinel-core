from langchain_experimental.tools import PythonREPLTool

from .base import BaseTool
from ...core.logger import get_logger

logger = get_logger(__name__)


def get_code_execution_tool() -> BaseTool:
    """
    코드 실행 도구 인스턴스를 생성하여 반환합니다. (플레이스홀더)
    """
    logger.info("Python REPL (Code Execution) 도구 초기화 완료.")
    return PythonREPLTool()
