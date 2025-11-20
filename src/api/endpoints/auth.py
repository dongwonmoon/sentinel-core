# -*- coding: utf-8 -*-
"""
API 라우터: 인증 (Authentication)

이 모듈은 사용자 인증과 관련된 모든 API 엔드포인트를 정의합니다.
- **/register**: 신규 사용자 등록 (회원가입)
- **/token**: 로그인 및 JWT 액세스 토큰 발급
- **/me**: 현재 로그인된 사용자 정보 조회
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, exc as sqlalchemy_exc

from .. import dependencies, schemas
from ...core import security
from ...core.logger import get_logger

router = APIRouter(prefix="", tags=["Authentication"])
logger = get_logger(__name__)


async def _get_user_from_db(
    session: AsyncSession, username: str
) -> schemas.UserInDB | None:
    """[헬퍼 함수] 데이터베이스에서 사용자 이름으로 사용자 정보를 조회합니다."""
    logger.debug(f"데이터베이스에서 사용자 '{username}' 조회를 시도합니다.")
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": username})
    user_row = result.fetchone()

    if user_row:
        logger.debug(f"데이터베이스에서 사용자 '{username}'를 찾았습니다.")
        # SQLAlchemy의 Row 객체를 Pydantic 모델로 변환하여 반환합니다.
        return schemas.UserInDB(**user_row._asdict())

    # 사용자를 찾지 못한 경우, 명시적으로 None을 반환하여 호출 측에서 처리하도록 합니다.
    logger.debug(f"데이터베이스에서 사용자 '{username}'를 찾을 수 없습니다.")
    return None


@router.post(
    "/register",
    response_model=schemas.User,
    status_code=status.HTTP_201_CREATED,
    summary="신규 사용자 등록",
)
async def register_user(
    user_create: schemas.UserCreate,
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.User:
    """
    새로운 사용자를 시스템에 등록합니다.
    """
    logger.info(f"새 사용자 등록을 시도합니다: '{user_create.username}'")

    # 1. 사용자 이름이 이미 존재하는지 확인하여 중복 가입을 방지합니다.
    db_user = await _get_user_from_db(session, user_create.username)
    if db_user:
        logger.warning(
            f"등록 실패: 사용자 이름 '{user_create.username}'이(가) 이미 존재합니다."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # 2. 비밀번호를 bcrypt를 사용하여 안전하게 해시합니다. 원본 비밀번호는 절대 저장하지 않습니다.
    hashed_password = security.get_password_hash(user_create.password)
    logger.debug(f"사용자 '{user_create.username}'의 비밀번호 해싱을 완료했습니다.")

    # 3. 새로운 사용자 정보를 데이터베이스에 삽입합니다.
    # `RETURNING` 절을 사용하여 삽입된 레코드의 정보를 즉시 반환받아,
    # 별도의 SELECT 쿼리 없이 응답 데이터를 구성할 수 있습니다.
    stmt = text(
        """
        INSERT INTO users (username, hashed_password, is_active)
        VALUES (:username, :hashed_password, :is_active)
        RETURNING user_id, username, is_active, created_at
    """
    )

    try:
        result = await session.execute(
            stmt,
            {
                "username": user_create.username,
                "hashed_password": hashed_password,
                "is_active": True,
            },
        )
        new_user_row = result.fetchone()
        if not new_user_row:
            # 삽입 후 RETURNING 절에서 데이터를 가져오지 못한 경우, 심각한 오류로 간주합니다.
            logger.error(
                f"사용자 '{user_create.username}' 삽입 후 데이터 조회를 실패했습니다."
            )
            raise HTTPException(
                status_code=500, detail="Failed to create user after insertion."
            )

        logger.info(
            f"사용자 '{user_create.username}' (ID: {new_user_row.user_id}) 등록에 성공했습니다."
        )
        return schemas.User(**new_user_row._asdict())

    except sqlalchemy_exc.IntegrityError:
        # 거의 동시에 동일한 사용자 이름으로 가입 요청이 들어올 경우,
        # 첫 번째 검사를 통과했더라도 DB의 UNIQUE 제약 조건에 의해 이 오류가 발생할 수 있습니다.
        logger.warning(
            f"등록 실패: 사용자 이름 '{user_create.username}'이(가) 이미 존재합니다 (IntegrityError)."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    except Exception as e:
        logger.exception(
            f"사용자 '{user_create.username}' 등록 중 예기치 않은 데이터베이스 오류가 발생했습니다."
        )
        raise HTTPException(status_code=500, detail=f"A database error occurred: {e}")


@router.post(
    "/token", response_model=schemas.Token, summary="로그인 및 액세스 토큰 발급"
)
async def login_for_access_token(
    # FastAPI의 `OAuth2PasswordRequestForm`은 'x-www-form-urlencoded' 형식의 요청 본문을
    # 파싱하여 사용자 이름과 비밀번호를 추출하는 편리한 의존성입니다.
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> Dict[str, str]:
    """
    사용자 이름과 비밀번호로 로그인하여 JWT 액세스 토큰을 발급받습니다.
    """
    username = form_data.username
    password = form_data.password
    logger.info(f"사용자 '{username}'의 로그인을 시도합니다.")

    # 1. 데이터베이스에서 사용자 정보를 조회합니다.
    user = await _get_user_from_db(session, username)

    # 2. 사용자가 존재하고, 제공된 비밀번호가 저장된 해시와 일치하는지 확인합니다.
    #    `verify_password`는 시간 일정 공격(timing attack)에 안전한 비교를 수행합니다.
    if not user or not security.verify_password(password, user.hashed_password):
        logger.warning(
            f"로그인 실패: 사용자 '{username}'의 사용자 이름 또는 비밀번호가 잘못되었습니다."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(f"로그인 실패: 사용자 '{username}'은(는) 비활성화된 계정입니다.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    # 3. JWT 액세스 토큰을 생성합니다.
    # 토큰의 페이로드(payload)에는 'sub'(subject, 사용자 이름)와 같은 표준 클레임과
    # 애플리케이션별 커스텀 데이터('permission_groups')를 포함할 수 있습니다.
    access_token_data = {
        "sub": user.username,
    }
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"사용자 '{user.username}' 로그인에 성공하여 토큰을 발급했습니다.")

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.User, summary="현재 사용자 정보 조회")
async def read_users_me(
    # 이 엔드포인트의 모든 로직은 `get_current_user` 의존성 내에 캡슐화되어 있습니다.
    # `Depends`가 `get_current_user`를 호출하고, 해당 함수가 토큰 검증 및
    # DB 조회를 모두 수행한 후, 유효한 사용자 객체를 `current_user` 매개변수에 주입합니다.
    # 만약 토큰이 유효하지 않으면 `get_current_user`가 직접 예외를 발생시키므로,
    # 이 함수의 본문은 실행되지 않습니다.
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
) -> schemas.User:
    """
    요청 헤더의 유효한 JWT 토큰을 기반으로 현재 로그인된 사용자의 정보를 반환합니다.
    """
    logger.info(
        f"인증된 사용자 '{current_user.username}'의 정보를 조회를 요청했습니다."
    )
    return current_user
