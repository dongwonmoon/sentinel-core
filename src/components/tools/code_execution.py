# -*- coding: utf-8 -*-
"""
LLM이 생성한 파이썬 코드를 안전하게 실행하기 위한 도구를 제공합니다.
"""

import re
import subprocess
import sys
from typing import Final

from langchain_experimental.tools import PythonREPLTool

from .base import BaseTool
from ...core.logger import get_logger

logger = get_logger(__name__)

# --- 보안 설정 상수 ---

# 서브프로세스에 전달될 환경 변수.
# PYTHONUNBUFFERED=1은 자식 프로세스의 출력이 버퍼링 없이 즉시 전달되도록 합니다.
ALLOWED_ENV: Final[dict[str, str]] = {"PYTHONUNBUFFERED": "1"}

# 코드 실행을 금지할 위험한 패턴 목록.
# 파일 시스템 접근, 네트워크, 서브프로세스 생성 등과 관련된 모듈 임포트 및 함수 호출을 차단합니다.
BANNED_CODE_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"__import__",  # `__import__` 내장 함수 직접 사용 금지
        r"import\s+os",  # os 모듈 임포트 금지
        r"import\s+sys",  # sys 모듈 임포트 금지 (일부 기능 제외)
        r"import\s+subprocess",  # subprocess 모듈 임포트 금지
        r"import\s+socket",  # socket 모듈 임포트 금지
        r"open\(",  # open() 함수를 사용한 파일 열기 금지
    )
]

# 실행할 코드의 최대 길이 (문자 수)
MAX_CODE_CHARS: Final[int] = 2000

# 코드 실행 최대 시간 (초)
EXECUTION_TIMEOUT_SECONDS: Final[int] = 5


class SafePythonREPLTool(PythonREPLTool):
    """
    길이/패턴/샌드박스 검증 등 여러 보안 계층을 적용하여 안전성을 강화한 Python REPL(Read-Eval-Print Loop) 도구입니다.
    LangChain의 `PythonREPLTool`을 상속받아, 코드 실행 로직(`_run` 메서드)을 오버라이드하여 구현합니다.
    """

    name: str = "code_execution"
    description: str = (
        "A Python shell. Use this to execute python code. "
        "Input should be a valid python command. "
        "Useful for performing calculations, data manipulations, etc. "
        "The code will be executed in a sandboxed environment."
    )

    def _validate_code(self, code: str) -> str:
        """
        실행 전 코드를 검증합니다. (길이, 금지 패턴)
        """
        cleaned = code.strip()
        if len(cleaned) > MAX_CODE_CHARS:
            logger.warning(
                f"코드 길이가 최대 허용치({MAX_CODE_CHARS})를 초과했습니다."
            )
            raise ValueError("Code snippet exceeds maximum allowed length.")

        lowered = cleaned.lower()
        for pattern in BANNED_CODE_PATTERNS:
            if pattern.search(lowered):
                logger.warning(
                    f"코드에 허용되지 않는 패턴이 포함되어 있습니다: {pattern.pattern}"
                )
                raise ValueError("Code snippet contains disallowed operations.")

        logger.debug("코드 유효성 검사를 통과했습니다.")
        return cleaned

    def _run(self, query: str) -> str:
        """
        주어진 파이썬 코드(query)를 안전하게 실행하고 그 결과를 반환합니다.

        보안을 위해, 코드는 격리된 환경의 서브프로세스에서 실행됩니다.
        - `-I` 플래그: 격리 모드(Isolated Mode)로 파이썬을 실행하여, 스크립트 디렉토리나 사용자 site-packages를 `sys.path`에 추가하지 않습니다.
        - `env=ALLOWED_ENV`: 최소한의 환경 변수만 허용합니다.
        - `timeout`: 지정된 시간 내에 실행이 완료되지 않으면 `TimeoutExpired` 예외를 발생시킵니다.
        """
        try:
            cleaned_code = self._validate_code(query)
        except ValueError as e:
            # 유효성 검사 실패 시, 오류 메시지를 결과로 반환하여 LLM이 문제를 인지하도록 합니다.
            return f"Validation Error: {e}"

        logger.info(
            f"안전한 코드 실행 요청 수락 (코드 길이: {len(cleaned_code)}자)"
        )

        try:
            # `subprocess.run`을 사용하여 안전한 샌드박스 환경에서 코드를 실행합니다.
            completed_process = subprocess.run(
                [sys.executable or "python3", "-I", "-c", cleaned_code],
                capture_output=True,  # stdout, stderr를 캡처
                text=True,  # 출력을 텍스트(str)로 디코딩
                timeout=EXECUTION_TIMEOUT_SECONDS,
                env=ALLOWED_ENV,
                check=False,  # returncode가 0이 아니어도 예외를 발생시키지 않음
            )
        except subprocess.TimeoutExpired as exc:
            logger.error(f"코드 실행 시간 초과 ({EXECUTION_TIMEOUT_SECONDS}초)")
            # 타임아웃 발생 시, 오류 메시지를 반환합니다.
            raise TimeoutError("Code execution timed out.") from exc
        except Exception as e:
            logger.error(
                f"코드 실행 중 예기치 않은 오류 발생: {e}", exc_info=True
            )
            raise RuntimeError(
                f"An unexpected error occurred during code execution: {e}"
            ) from e

        # 실행 결과 처리
        if completed_process.returncode != 0:
            # 코드가 오류와 함께 종료된 경우
            stderr = completed_process.stderr.strip()
            logger.warning(f"코드 실행 실패. Stderr: {stderr[:200]}...")
            # LLM이 오류를 이해하고 수정할 수 있도록 stderr 내용을 반환합니다.
            return f"Execution failed with error: {stderr}"

        # 성공적으로 실행된 경우, stdout 출력을 반환합니다.
        stdout = completed_process.stdout.strip()
        logger.info(f"코드 실행 성공. Stdout: {stdout[:200]}...")
        return stdout

    def to_tool_string(self) -> str:
        return f"- {self.name}: {self.description}"


def get_code_execution_tool() -> BaseTool:
    """
    안전 가드(Safety Guard)가 적용된 Python REPL 도구 인스턴스를 생성합니다.
    """
    try:
        tool = SafePythonREPLTool()
        logger.info(
            "Python REPL (Code Execution) 도구 초기화가 완료되었습니다."
        )
        return tool
    except Exception as e:
        logger.error(
            f"Python REPL 도구 초기화 중 오류 발생: {e}", exc_info=True
        )
        raise
