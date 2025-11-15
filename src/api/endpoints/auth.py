# -*- coding: utf-8 -*-
"""
API 라우터: 인증 (Authentication)

이 모듈은 사용자 인증과 관련된 모든 API 엔드포인트를 정의합니다.
- **/register**: 신규 사용자 등록 (회원가입)
- **/token**: 로그인 및 JWT 액세스 토큰 발급
- **/me**: 현재 로그인된 사용자 정보 조회
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, exc as sqlalchemy_exc

from .. import dependencies, schemas
from ...core import security
from ...core.logger import get_logger

# '/auth' 접두사를 가진 APIRouter를 생성합니다.
router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


async def _get_user_from_db(session: AsyncSession, username: str) -> schemas.UserInDB | None:
    """[헬퍼 함수] 데이터베이스에서 사용자 이름으로 사용자 정보를 조회합니다."""
    logger.debug(f"데이터베이스에서 사용자 '{username}' 조회를 시도합니다.")
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": username})
    user_row = result.fetchone()
    
    if user_row:
        logger.debug(f"데이터베이스에서 사용자 '{username}'를 찾았습니다.")
        return schemas.UserInDB(**user_row._asdict())
    
    logger.debug(f"데이터베이스에서 사용자 '{username}'를 찾을 수 없습니다.")
    return None


@router.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED, summary="신규 사용자 등록")
async def register_user(
    user_create: schemas.UserCreate,
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.User:
    """
    새로운 사용자를 시스템에 등록합니다.
    """
    logger.info(f"새 사용자 등록을 시도합니다: '{user_create.username}'")
    
    # 1. 사용자 이름이 이미 존재하는지 확인합니다.
    db_user = await _get_user_from_db(session, user_create.username)
    if db_user:
        logger.warning(f"등록 실패: 사용자 이름 '{user_create.username}'이(가) 이미 존재합니다.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # 2. 비밀번호를 안전하게 해시합니다.
    hashed_password = security.get_password_hash(user_create.password)
    logger.debug(f"사용자 '{user_create.username}'의 비밀번호 해싱을 완료했습니다.")

    # 3. 새로운 사용자 정보를 데이터베이스에 삽입합니다.
    stmt = text("""
        INSERT INTO users (username, hashed_password, is_active, permission_groups)
        VALUES (:username, :hashed_password, :is_active, :permission_groups)
        RETURNING user_id, username, is_active, permission_groups, created_at
    """)
    
    try:
        result = await session.execute(
            stmt,
            {
                "username": user_create.username,
                "hashed_password": hashed_password,
                "is_active": True,
                "permission_groups": user_create.permission_groups or ["all_users"],
            },
        )
        new_user_row = result.fetchone()
        if not new_user_row:
            # 삽입 후 RETURNING 절에서 데이터를 가져오지 못한 경우, 심각한 오류로 간주합니다.
            logger.error(f"사용자 '{user_create.username}' 삽입 후 데이터 조회를 실패했습니다.")
            raise HTTPException(status_code=500, detail="Failed to create user after insertion.")
            
        logger.info(f"사용자 '{user_create.username}' (ID: {new_user_row.user_id}) 등록에 성공했습니다.")
        return schemas.User(**new_user_row._asdict())

    except sqlalchemy_exc.IntegrityError:
        # 동시성 문제 등으로 인해 사용자 이름이 중복될 경우를 처리합니다.
        logger.warning(f"등록 실패: 사용자 이름 '{user_create.username}'이(가) 이미 존재합니다 (IntegrityError).")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    except Exception as e:
        logger.exception(f"사용자 '{user_create.username}' 등록 중 예기치 않은 데이터베이스 오류가 발생했습니다.")
        raise HTTPException(status_code=500, detail=f"A database error occurred: {e}")


@router.post("/token", response_model=schemas.Token, summary="로그인 및 액세스 토큰 발급")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> Dict[str, str]:
    """
    사용자 이름과 비밀번호로 로그인하여 JWT 액세스 토큰을 발급받습니다.
    FastAPI의 `OAuth2PasswordRequestForm`은 'x-www-form-urlencoded' 형식의 요청 본문을 처리합니다.
    """
    username = form_data.username
    password = form_data.password
    logger.info(f"사용자 '{username}'의 로그인을 시도합니다.")

    # 1. 데이터베이스에서 사용자 정보를 조회합니다.
    user = await _get_user_from_db(session, username)
    
    # 2. 사용자가 존재하고, 제공된 비밀번호가 저장된 해시와 일치하는지 확인합니다.
    if not user or not security.verify_password(password, user.hashed_password):
        logger.warning(f"로그인 실패: 사용자 '{username}'의 사용자 이름 또는 비밀번호가 잘못되었습니다.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        logger.warning(f"로그인 실패: 사용자 '{username}'은(는) 비활성화된 계정입니다.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    # 3. JWT 액세스 토큰을 생성합니다.
    # 토큰의 payload에는 'sub'(subject, 사용자 이름)와 같은 표준 클레임과
    # 커스텀 데이터('permission_groups')를 포함할 수 있습니다.
    access_token_data = {
        "sub": user.username,
        "permission_groups": user.permission_groups,
    }
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"사용자 '{user.username}' 로그인에 성공하여 토큰을 발급했습니다.")

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.User, summary="현재 사용자 정보 조회")
async def read_users_me(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
) -> schemas.User:
    """
    요청 헤더의 유효한 JWT 토큰을 기반으로 현재 로그인된 사용자의 정보를 반환합니다.
    `get_current_user` 의존성이 토큰 검증 및 사용자 정보 조회를 모두 처리합니다.
    """
    logger.info(f"인증된 사용자 '{current_user.username}'의 정보를 조회를 요청했습니다.")
    return current_user
