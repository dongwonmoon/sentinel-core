# -*- coding: utf-8 -*-
"""
애플리케이션 전반에서 사용될 로거(Logger)를 설정하고 관리하는 모듈입니다.

이 모듈의 핵심 기능:
1.  **중앙화된 로거 설정**: `get_logger` 함수를 통해 일관된 포맷과 레벨을 가진 로거를 생성합니다.
2.  **설정 파일 연동**: `config.py`에 정의된 `log_level`과 `log_format` 값을 동적으로 읽어와 로거에 적용합니다.
3.  **핸들러 중복 방지**: 로거에 핸들러가 이미 설정되어 있는지 확인하여, 동일한 로그가 여러 번 출력되는 것을 방지합니다.
"""

import logging
import sys

from .config import get_settings

# get_settings()를 호출하여 설정 객체를 가져옵니다.
# 이 시점에서 config.py의 로직에 따라 설정이 로드되고 캐시됩니다.
settings = get_settings()


def get_logger(name: str) -> logging.Logger:
    """
    설정된 포맷과 레벨을 가진 로거 인스턴스를 생성하거나 기존 인스턴스를 반환합니다.

    Python의 `logging` 모듈은 이름 기반으로 로거를 관리하므로, 동일한 이름으로
    `getLogger`를 여러 번 호출해도 항상 같은 로거 객체를 반환합니다.

    이 함수는 그 위에 핸들러(Handler)가 중복으로 추가되는 것을 방지하고,
    `config.yml` 파일의 설정을 적용하는 역할을 추가로 수행합니다.

    Args:
        name (str): 로거의 이름.
                    일반적으로 호출하는 모듈의 `__name__`을 전달하여,
                    로그 출력 시 어떤 모듈에서 로그가 발생했는지 쉽게 추적할 수 있도록 합니다.

    Returns:
        logging.Logger: 설정이 완료된 로거 객체.
    """
    # 이름(name)을 기준으로 로거 인스턴스를 가져옵니다.
    # 같은 이름의 로거가 이미 생성되었다면 기존 객체를, 없다면 새로 생성하여 반환합니다.
    logger = logging.getLogger(name)

    # 로거에 핸들러가 이미 설정되어 있는지 확인합니다.
    # 이 검사를 통해, 동일한 로거에 스트림 핸들러가 여러 번 추가되어
    # 같은 로그 메시지가 중복으로 출력되는 현상을 방지합니다.
    if not logger.handlers:
        # 설정 파일(config.yml)에서 로그 레벨 문자열(예: "INFO")을 가져옵니다.
        # `getattr`를 사용하여 `logging.INFO`와 같은 실제 로깅 레벨 상수로 변환합니다.
        # 만약 설정된 값이 유효하지 않으면 기본값으로 `logging.INFO`를 사용합니다.
        log_level_str = settings.app.log_level.upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)

        # 로그 메시지 포맷을 설정 파일에서 가져와 Formatter 객체를 생성합니다.
        formatter = logging.Formatter(settings.app.log_format)

        # 로그를 콘솔(표준 출력, stdout)으로 보내는 StreamHandler를 생성합니다.
        # 파일 로깅, 외부 로깅 서비스(예: Sentry, Datadog) 연동 등
        # 다른 핸들러를 추가하고 싶다면 이 부분에서 구성할 수 있습니다.
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)  # 핸들러에 포맷을 적용합니다.

        # 최종적으로 로거에 핸들러를 추가합니다.
        # 이 로거를 통해 출력되는 모든 로그는 이 핸들러를 거쳐 처리됩니다.
        logger.addHandler(handler)

        logger.debug(
            f"'{name}' 로거가 '{log_level_str}' 레벨로 초기화되었습니다."
        )

    return logger
