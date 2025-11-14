"""
API 계층에서 사용되는 모든 Pydantic 모델(스키마)을 정의합니다.
이 스키마들은 API의 요청 본문(Request Body)과 응답 본문(Response Body)의 형태를 결정하고,
FastAPI의 자동 문서 생성(Swagger UI)에 사용됩니다.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Literal

from pydantic import BaseModel, Field, HttpUrl


# --- 1. 인증 (Authentication) 관련 스키마 ---


class Token(BaseModel):
    """JWT 토큰 응답 스키마"""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """JWT 토큰에 저장될 데이터 (페이로드)"""

    username: Optional[str] = None
    permission_groups: Optional[List[str]] = None


class UserBase(BaseModel):
    """사용자 기본 스키마"""

    username: str


class UserCreate(UserBase):
    """사용자 생성(회원가입) 요청 스키마"""

    password: str
    permission_groups: List[str] = Field(default_factory=lambda: ["all_users"])


class User(UserBase):
    """API 응답용 사용자 정보 스키마 (비밀번호 제외)"""

    user_id: int
    is_active: bool
    permission_groups: List[str]

    class Config:
        orm_mode = True  # SQLAlchemy 모델과 호환


class UserInDB(User):
    """DB에 저장된 사용자 모델 (해시된 비밀번호 포함)"""

    hashed_password: str


# --- 2. 채팅 (Chat) 관련 스키마 ---


class ChatMessageBase(BaseModel):
    """채팅 메시지의 기본 스키마"""

    role: Literal["user", "assistant"]
    content: str


class ChatMessageInDB(ChatMessageBase):
    """DB에서 읽어올 때 사용할 스키마 (생성 시간 포함)"""

    created_at: datetime

    class Config:
        orm_mode = True


class ChatHistoryResponse(BaseModel):
    """GET /chat-history 응답 스키마"""

    messages: List[ChatMessageInDB]


class ChatSession(BaseModel):
    """GET /chat/sessions 응답의 개별 세션 정보"""

    session_id: str
    title: str  # 세션의 첫 번째 사용자 메시지
    last_updated: datetime  # 세션의 마지막 활동 시간

    class Config:
        orm_mode = True


class ChatSessionListResponse(BaseModel):
    """GET /chat/sessions 응답 스키마"""

    sessions: List[ChatSession]


class QueryRequest(BaseModel):
    """POST /query/corporate 요청 스키마"""

    query: str = Field(..., description="사용자의 질문")
    top_k: int = Field(default=3, description="RAG 검색 시 반환할 최종 청크 수")
    doc_ids_filter: Optional[List[str]] = Field(
        default=None, description="RAG 검색을 제한할 문서 ID 리스트"
    )
    chat_history: Optional[List[ChatMessageBase]] = Field(
        default=None, description="이전 대화 기록"
    )
    session_id: Optional[str] = Field(
        default=None, description="현재 대화 세션을 식별하는 ID"
    )


class Source(BaseModel):
    """답변의 출처 정보를 담는 스키마"""

    page_content: str
    metadata: Dict[str, Any]
    score: float


# --- 3. 문서 (Documents) 관련 스키마 ---


class GitHubRepoRequest(BaseModel):
    """POST /index-github-repo 요청 스키마"""

    repo_url: HttpUrl = Field(..., description="인덱싱할 GitHub 저장소의 URL")


class DeleteDocumentRequest(BaseModel):
    """DELETE /documents 요청 스키마"""

    doc_id_or_prefix: str = Field(..., description="삭제할 doc_id 또는 접두사")


class DocumentResponse(BaseModel):
    """GET /documents 응답 스키마의 각 항목"""

    filter_key: str
    display_name: str
