import re
import subprocess
import sys
from typing import Final

from langchain_experimental.tools import PythonREPLTool

from .base import BaseTool
from ...core.logger import get_logger

logger = get_logger(__name__)

ALLOWED_ENV: Final[dict[str, str]] = {"PYTHONUNBUFFERED": "1"}
BANNED_CODE_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"__import__",
        r"import\s+os",
        r"import\s+sys",
        r"import\s+subprocess",
        r"import\s+socket",
        r"open\(.*\)",
    )
]
MAX_CODE_CHARS: Final[int] = 2000
EXECUTION_TIMEOUT_SECONDS: Final[int] = 5


class SafePythonREPLTool(PythonREPLTool):
    """길이/패턴/샌드박스 검증을 적용한 Python REPL 도구."""

    name: str = "python_repl"

    def _validate_code(self, code: str) -> str:
        cleaned = code.strip()
        if len(cleaned) > MAX_CODE_CHARS:
            raise ValueError("Code snippet exceeds maximum allowed length.")
        lowered = cleaned.lower()
        for pattern in BANNED_CODE_PATTERNS:
            if pattern.search(lowered):
                raise ValueError("Code snippet contains disallowed operations.")
        return cleaned

    def _run(self, query: str) -> str:  # type: ignore[override]
        cleaned = self._validate_code(query)
        logger.info("Code execution request accepted (chars=%d)", len(cleaned))
        try:
            completed = subprocess.run(
                [sys.executable or "python3", "-I", "-c", cleaned],
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT_SECONDS,
                env=ALLOWED_ENV,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error(
                "Code execution timed out after %ss", EXECUTION_TIMEOUT_SECONDS
            )
            raise TimeoutError("Code execution timed out.") from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            logger.warning("Code execution failed: %s", stderr[:200])
            raise RuntimeError(f"Code execution failed: {stderr}")

        return completed.stdout.strip()


def get_code_execution_tool() -> BaseTool:
    """안전 가드를 적용한 Python REPL 도구 인스턴스를 생성합니다."""
    tool = SafePythonREPLTool()
    logger.info("Python REPL (Code Execution) 도구 초기화 완료.")
    return tool
