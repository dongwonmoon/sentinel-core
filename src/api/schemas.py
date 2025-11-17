# -*- coding: utf-8 -*-
"""
API 계층에서 사용되는 모든 Pydantic 모델(스키마)을 정의합니다.

이 스키마들은 API의 요청 본문(Request Body)과 응답 본문(Response Body)의
데이터 유효성을 검사하고, 형태를 강제하는 역할을 합니다. 이를 통해 API의 안정성과
예측 가능성을 높입니다. 또한, FastAPI의 자동 문서 생성(Swagger UI/ReDoc)의
기반이 되어, 개발자들이 API 명세를 쉽게 확인하고 테스트할 수 있도록 돕습니다.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Literal

from pydantic import BaseModel, Field, HttpUrl


# --- 1. 인증 (Authentication) 관련 스키마 ---


class Token(BaseModel):
    """JWT 토큰 응답 스키마"""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """JWT 토큰에 저장될 데이터 (페이로드)"""

    username: Optional[str] = None
    permission_groups: Optional[List[str]] = None


class UserBase(BaseModel):
    """사용자 기본 스키마"""

    username: str


class UserCreate(UserBase):
    """사용자 생성(회원가입) 요청 스키마"""

    password: str = Field(...)
    permission_groups: List[str] = Field(default_factory=lambda: ["all_users"])


class User(UserBase):
    """
    API 응답용 사용자 정보 스키마입니다.
    보안을 위해 해시된 비밀번호와 같은 민감한 정보는 이 스키마에서 제외됩니다.
    """

    user_id: int
    is_active: bool
    permission_groups: List[str]
    created_at: datetime

    # Pydantic V2 설정: SQLAlchemy 모델 객체(ORM 모델)로부터 Pydantic 모델을 직접 생성할 수 있도록 허용합니다.
    # 이를 통해 `User.model_validate(orm_user)`와 같은 코드가 가능해집니다.
    model_config = {"from_attributes": True}


class UserInDB(User):
    """
    데이터베이스에 저장된 전체 사용자 정보를 나타내는 스키마입니다.
    API 응답에는 직접 사용되지 않으며, 주로 내부 로직에서 사용됩니다.
    """

    hashed_password: str
    profile_text: Optional[str] = None


# --- 2. 채팅 (Chat) 관련 스키마 ---


class ChatMessageBase(BaseModel):
    """채팅 메시지의 기본 스키마"""

    role: Literal["user", "assistant"]
    content: str


class ChatMessageInDB(ChatMessageBase):
    """DB에서 읽어올 때 사용할 스키마 (생성 시간 포함)"""

    created_at: datetime
    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    """GET /chat/history 응답 스키마"""

    messages: List[ChatMessageInDB]


class ChatSession(BaseModel):
    """GET /chat/sessions 응답의 개별 세션 정보"""

    session_id: str
    title: str
    last_updated: datetime
    model_config = {"from_attributes": True}


class ChatSessionListResponse(BaseModel):
    """GET /chat/sessions 응답 스키마"""

    sessions: List[ChatSession]


class QueryRequest(BaseModel):
    """POST /query 요청 스키마"""

    query: str = Field(..., description="사용자의 질문")
    top_k: int = Field(default=3, description="RAG 검색 시 반환할 최종 청크 수")
    session_id: Optional[str] = Field(
        default=None, description="현재 대화 세션을 식별하는 ID"
    )


class SessionContextUpdate(BaseModel):
    """PUT /chat/sessions/{session_id}/context 요청 스키마"""

    doc_ids_filter: Optional[List[str]] = Field(
        default=None, description="RAG 검색을 제한할 문서 ID 리스트"
    )


class Source(BaseModel):
    """답변의 출처(Source) 정보를 담는 스키마입니다."""

    chunk_text: str = Field(
        ..., description="RAG를 통해 검색된 원본 텍스트 청크"
    )
    metadata: Dict[str, Any] = Field(
        ..., description="청크에 대한 추가 정보 (예: 파일명, 페이지 번호)"
    )
    score: float = Field(
        ..., description="쿼리와의 유사도 점수 (높을수록 관련성 높음)"
    )


class UserProfileResponse(BaseModel):
    """GET /chat/profile 응답 스키마"""

    profile_text: Optional[str] = None


class UserProfileUpdate(BaseModel):
    """POST /chat/profile 요청 스키마"""

    profile_text: str


# --- 3. 첨부/업로드 관련 스키마 ---


class GitHubRepoRequest(BaseModel):
    """POST /index-github-repo 요청 스키마"""

    # Pydantic의 `HttpUrl` 타입을 사용하여 입력된 URL이 유효한 형식인지 자동으로 검증합니다.
    repo_url: HttpUrl = Field(..., description="인덱싱할 GitHub 저장소의 URL")


class SessionAttachmentResponse(BaseModel):
    """세션 첨부파일 정보"""

    attachment_id: int
    file_name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionAttachmentListResponse(BaseModel):
    """세션 첨부파일 목록 응답"""

    attachments: List[SessionAttachmentResponse]
