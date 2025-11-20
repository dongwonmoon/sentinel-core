"""
애플리케이션의 핵심 보안 로직을 담당하는 모듈입니다.
- 비밀번호 해싱 및 검증
- JWT 토큰 생성 및 검증
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()
from ..api.schemas import TokenData


# --- 1. 비밀번호 해싱 설정 ---
# `bcrypt`는 현재 산업 표준으로 널리 사용되는 안전한 해싱 알고리즘입니다.
# 키 스트레칭(key stretching)을 지원하여 브루트포스 공격에 대한 저항력을 높입니다.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- 2. 보안 유틸리티 함수 ---


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """일반 비밀번호와 해시된 비밀번호를 비교합니다."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """일반 비밀번호를 해시합니다."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """주어진 데이터를 바탕으로 JWT Access Token을 생성합니다."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    # 'exp' (만료 시간) 클레임을 추가합니다. 이 클레임은 토큰이 유효한 기간을 정의합니다.
    to_encode.update({"exp": expire})
    # 비밀 키와 지정된 알고리즘을 사용하여 JWT를 인코딩(서명)합니다.
    return jwt.encode(
        to_encode, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM
    )


def verify_token(token: str, credentials_exception: Exception) -> TokenData:
    """JWT 토큰을 검증하고, 유효하면 페이로드(TokenData)를 반환합니다."""
    try:
        # `jwt.decode`는 토큰의 서명과 만료 시간을 자동으로 검증합니다.
        # 서명이 유효하지 않거나 토큰이 만료된 경우 `JWTError` 예외가 발생합니다.
        payload = jwt.decode(
            token,
            settings.AUTH_SECRET_KEY,
            algorithms=[settings.AUTH_ALGORITHM],
        )
        # 페이로드에서 사용자 이름('sub' 클레임)을 추출합니다.
        username: str = payload.get("sub")

        if username is None:
            # 토큰에 사용자 이름이 없는 경우, 유효하지 않은 토큰으로 간주합니다.
            raise credentials_exception

        # 추출된 정보를 Pydantic 모델로 래핑하여 반환합니다.
        return TokenData(username=username)
    except JWTError:
        # 토큰 검증 실패 시, 미리 전달받은 인증 예외를 발생시킵니다.
        raise credentials_exception
