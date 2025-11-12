# src/logger.py
import logging
import sys

from .config import settings

def get_logger(name: str) -> logging.Logger:
    """
    설정된 포맷과 레벨을 가진 로거 인스턴스를 생성하고 반환합니다.

    Args:
        name: 로거의 이름 (일반적으로 __name__을 사용).

    Returns:
        설정된 logging.Logger 객체.
    """
    # 로거를 가져옵니다.
    logger = logging.getLogger(name)
    
    # 로거에 핸들러가 이미 설정되어 있는지 확인하여 중복 추가를 방지합니다.
    if not logger.handlers:
        # 로그 레벨을 config에서 읽어와 설정합니다.
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)

        # 로그 메시지 포맷을 설정합니다.
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 로그를 콘솔(stdout)으로 보내는 핸들러를 생성합니다.
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        
        # 로거에 핸들러를 추가합니다.
        logger.addHandler(handler)

    return logger
