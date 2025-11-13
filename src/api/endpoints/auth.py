"""
API 라우터: 인증 (Authentication)
- /token: 로그인 및 JWT 토큰 발급
- /register: 신규 사용자 등록
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .. import dependencies, schemas
from ...core import security

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

async def _get_user_from_db(session: AsyncSession, username: str) -> schemas.UserInDB | None:
    """DB에서 사용자 정보를 조회하는 헬퍼 함수."""
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": username})
    user_row = result.fetchone()
    if user_row:
        return schemas.UserInDB(**user_row._asdict())
    return None


@router.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: schemas.UserCreate,
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """신규 사용자 등록 (회원가입)."""
    db_user = await _get_user_from_db(session, user_create.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = security.get_password_hash(user_create.password)
    
    # user_id는 serial primary key이므로 명시적으로 전달할 필요 없음
    stmt = text("""
        INSERT INTO users (username, hashed_password, is_active, permission_groups)
        VALUES (:username, :hashed_password, :is_active, :permission_groups)
        RETURNING user_id, username, is_active, permission_groups
    """)
    
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
            raise HTTPException(status_code=500, detail="Failed to create user.")
            
        return schemas.User(**new_user_row._asdict())

    except Exception as e:
        # DB 제약 조건 위반 등
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """
    사용자 로그인 (JWT 토큰 발급).
    OAuth2PasswordRequestForm을 사용하여 'x-www-form-urlencoded' 형식으로 요청받음.
    """
    user = await _get_user_from_db(session, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 토큰에 username과 실제 권한 그룹을 저장
    access_token_data = {
        "sub": user.username,
        "permission_groups": user.permission_groups,
    }
    access_token = security.create_access_token(data=access_token_data)

    return {"access_token": access_token, "token_type": "bearer"}
