"""
애플리케이션의 핵심 보안 로직을 담당하는 모듈입니다.
- 비밀번호 해싱 및 검증
- JWT 토큰 생성 및 검증
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..api.schemas import TokenData
from .config import get_settings

settings = get_settings()


# --- 1. 비밀번호 해싱 설정 ---
# `bcrypt`는 현재 산업 표준으로 널리 사용되는 안전한 해싱 알고리즘입니다.
# 키 스트레칭(key stretching)을 지원하여 브루트포스 공격에 대한 저항력을 높입니다.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- 2. 보안 유틸리티 함수 ---


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력된 평문 비밀번호가 해시된 비밀번호와 일치하는지 검증합니다."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """평문 비밀번호를 bcrypt 해시로 변환합니다."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """주어진 데이터(페이로드)를 포함하는 JWT Access Token을 생성합니다.

    Args:
        data (dict): 토큰의 페이로드에 포함될 데이터. 'sub' 클레임(주체)을 포함해야 합니다.
        expires_delta (Optional[timedelta]): 토큰의 만료 시간을 지정합니다.
                                             None이면 설정 파일의 기본값을 사용합니다.

    Returns:
        str: 생성된 JWT 문자열.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # 설정 파일에 정의된 기본 만료 시간을 사용합니다.
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str, credentials_exception: Exception) -> TokenData:
    """JWT 토큰의 유효성을 검사하고 페이로드에서 사용자 정보를 추출합니다.

    토큰의 서명, 만료 시간, 그리고 'sub' 클레임의 존재 여부를 확인합니다.
    검증에 실패하면, FastAPI 엔드포인트에서 처리할 수 있도록
    미리 주입된 `credentials_exception`을 발생시킵니다.

    Args:
        token (str): 검증할 JWT 토큰.
        credentials_exception (Exception): 검증 실패 시 발생시킬 예외.

    Returns:
        TokenData: 사용자 이름('sub')이 포함된 Pydantic 모델.
    """
    try:
        payload = jwt.decode(
            token,
            settings.AUTH_SECRET_KEY,
            algorithms=[settings.AUTH_ALGORITHM],
        )
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception

        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    return token_data
