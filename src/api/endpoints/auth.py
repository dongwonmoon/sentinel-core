"""
API 라우터: 인증 (Authentication)
- /auth/token: 로그인 및 JWT 토큰 발급
- /auth/register: 신규 사용자 등록
- /auth/me: 현재 로그인된 사용자 정보 조회
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .. import dependencies, schemas
from ...core import security
from ...core.logger import get_logger

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

logger = get_logger(__name__)


async def _get_user_from_db(
    session: AsyncSession, username: str
) -> schemas.UserInDB | None:
    """DB에서 사용자 정보를 조회하는 헬퍼 함수."""
    logger.debug(f"데이터베이스에서 사용자 '{username}' 조회 시도.")
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": username})
    user_row = result.fetchone()
    if user_row:
        logger.debug(f"데이터베이스에서 사용자 '{username}' 발견.")
        return schemas.UserInDB(**user_row._asdict())
    logger.debug(f"데이터베이스에서 사용자 '{username}'를 찾을 수 없음.")
    return None


@router.post(
    "/register",
    response_model=schemas.User,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    user_create: schemas.UserCreate,
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """신규 사용자 등록 (회원가입)."""
    logger.info(f"새 사용자 등록 시도: {user_create.username}")
    db_user = await _get_user_from_db(session, user_create.username)
    if db_user:
        logger.warning(f"등록 실패: 사용자명 '{user_create.username}'은 이미 등록됨.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = security.get_password_hash(user_create.password)
    logger.debug(f"사용자 '{user_create.username}'의 비밀번호 해싱 완료.")

    stmt = text(
        """
        INSERT INTO users (username, hashed_password, is_active, permission_groups)
        VALUES (:username, :hashed_password, :is_active, :permission_groups)
        RETURNING user_id, username, is_active, permission_groups
    """
    )

    try:
        result = await session.execute(
            stmt,
            {
                "username": user_create.username,
                "hashed_password": hashed_password,
                "is_active": True,
                "permission_groups": user_create.permission_groups,
            },
        )
        new_user_row = result.fetchone()
        if not new_user_row:
            logger.error(f"사용자 '{user_create.username}' 삽입 후 새 사용자 데이터 검색 실패.")
            raise HTTPException(
                status_code=500, detail="Failed to create user."
            )
        logger.info(f"사용자 '{user_create.username}' 등록 성공.")
        return schemas.User(**new_user_row._asdict())

    except Exception as e:
        logger.exception(f"사용자 '{user_create.username}' 등록 중 데이터베이스 오류 발생.")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """사용자 로그인 (JWT 토큰 발급)."""
    logger.info(f"사용자 '{form_data.username}' 로그인 시도.")
    user = await _get_user_from_db(session, form_data.username)
    if not user:
        logger.warning(f"로그인 실패: 사용자 '{form_data.username}'를 찾을 수 없음.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not security.verify_password(
        form_data.password, user.hashed_password
    ):
        logger.warning(f"로그인 실패: 사용자 '{form_data.username}'의 비밀번호가 일치하지 않음.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_data = {
        "sub": user.username,
        "permission_groups": user.permission_groups,
    }
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"사용자 '{user.username}' 로그인 성공. 토큰 발급 완료.")

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.User)
async def read_users_me(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
):
    """현재 로그인된 사용자의 정보를 반환합니다."""
    logger.info(f"사용자 '{current_user.username}'의 현재 사용자 정보 조회.")
    return current_user
