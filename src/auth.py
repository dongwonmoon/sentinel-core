import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Union

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from .config import settings  # 설정 파일에서 비밀 키 등을 가져옴
from .logger import get_logger

logger = get_logger(__name__)


# --- 1. 비밀번호 해싱 설정 ---
# bcrypt 알고리즘 사용
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 2. Pydantic 모델 (데이터 형태 정의) ---


class Token(BaseModel):
    """JWT 토큰 응답 모델"""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """JWT 토큰에 저장될 데이터 (페이로드)"""

    username: Optional[str] = None
    permission_groups: Optional[List[str]] = None


class User(BaseModel):
    """사용자 기본 모델"""

    username: str
    is_active: bool = True
    permission_groups: List[str] = Field(default_factory=lambda: ["all_users"])


class UserInDB(User):
    """DB에 저장된 사용자 모델 (해시된 비밀번호 포함)"""

    user_id: int
    hashed_password: str


class UserCreate(BaseModel):
    """사용자 생성(회원가입) 요청 모델"""

    username: str
    password: str
    # 관리자가 사용자를 생성할 때 권한 그룹을 지정할 수 있도록 함
    permission_groups: List[str] = Field(default_factory=lambda: ["all_users"])


# --- 3. 보안 유틸리티 함수 ---


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """일반 비밀번호와 해시된 비밀번호를 비교합니다."""
    logger.info(f"plain_password: {plain_password}, hashed_password: {hashed_password}")
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """일반 비밀번호를 해시합니다."""
    logger.info(f"password: {password}")
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    주어진 데이터를 바탕으로 JWT Access Token을 생성합니다.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # 설정 파일에서 가져온 기본 만료 시간 사용
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str, credentials_exception: Exception) -> TokenData:
    """
    JWT 토큰을 검증하고, 유효하면 페이로드(TokenData)를 반환합니다.
    """
    try:
        payload = jwt.decode(
            token, settings.AUTH_SECRET_KEY, algorithms=[settings.AUTH_ALGORITHM]
        )
        username: str = payload.get("sub")
        permission_groups: List[str] = payload.get("permission_groups", ["all_users"])

        if username is None:
            raise credentials_exception

        token_data = TokenData(username=username, permission_groups=permission_groups)
    except JWTError:
        raise credentials_exception

    return token_data
