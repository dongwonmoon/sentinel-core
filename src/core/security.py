"""
애플리케이션의 핵심 보안 로직을 담당하는 모듈입니다.
- 비밀번호 해싱 및 검증
- JWT 토큰 생성 및 검증
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from ..api.schemas import TokenData


# --- 1. 비밀번호 해싱 설정 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- 2. 보안 유틸리티 함수 ---


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """일반 비밀번호와 해시된 비밀번호를 비교합니다."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """일반 비밀번호를 해시합니다."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """주어진 데이터를 바탕으로 JWT Access Token을 생성합니다."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM
    )


def verify_token(token: str, credentials_exception: Exception) -> TokenData:
    """JWT 토큰을 검증하고, 유효하면 페이로드(TokenData)를 반환합니다."""
    try:
        payload = jwt.decode(
            token,
            settings.AUTH_SECRET_KEY,
            algorithms=[settings.AUTH_ALGORITHM],
        )
        username: str = payload.get("sub")
        permission_groups: List[str] = payload.get(
            "permission_groups", ["all_users"]
        )

        if username is None:
            raise credentials_exception

        return TokenData(username=username, permission_groups=permission_groups)
    except JWTError:
        raise credentials_exception
