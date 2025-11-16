# -*- coding: utf-8 -*-
"""
API 계층에서 사용되는 모든 Pydantic 모델(스키마)을 정의합니다.

이 스키마들은 API의 요청 본문(Request Body)과 응답 본문(Response Body)의
데이터 유효성을 검사하고, 형태를 강제하는 역할을 합니다.
또한, FastAPI의 자동 문서 생성(Swagger UI/ReDoc)의 기반이 됩니다.
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

    password: str = Field(..., min_length=8)
    permission_groups: List[str] = Field(default_factory=lambda: ["all_users"])


class User(UserBase):
    """API 응답용 사용자 정보 스키마 (비밀번호 제외)"""

    user_id: int
    is_active: bool
    permission_groups: List[str]
    created_at: datetime

    # Pydantic V2 설정: SQLAlchemy 모델 객체로부터 Pydantic 모델을 생성할 수 있도록 허용
    model_config = {"from_attributes": True}


class UserInDB(User):
    """DB에 저장된 사용자 모델 (해시된 비밀번호 포함)"""

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
    # doc_ids_filter: Optional[List[str]] = Field(
    #     default=None, description="RAG 검색을 제한할 문서 ID 리스트"
    # )
    # chat_history: Optional[List[ChatMessageBase]] = Field(
    #     default=None, description="이전 대화 기록"
    # )
    session_id: Optional[str] = Field(
        default=None, description="현재 대화 세션을 식별하는 ID"
    )


class SessionContextUpdate(BaseModel):
    """PUT /chat/sessions/{session_id}/context 요청 스키마"""

    doc_ids_filter: Optional[List[str]] = Field(
        default=None, description="RAG 검색을 제한할 문서 ID 리스트"
    )


class Source(BaseModel):
    """답변의 출처 정보를 담는 스키마"""

    chunk_text: str
    metadata: Dict[str, Any]
    score: float


class UserProfileResponse(BaseModel):
    """GET /chat/profile 응답 스키마"""

    profile_text: Optional[str] = None


class UserProfileUpdate(BaseModel):
    """POST /chat/profile 요청 스키마"""

    profile_text: str


# --- 3. 문서 (Documents) 관련 스키마 ---


class GitHubRepoRequest(BaseModel):
    """POST /index-github-repo 요청 스키마"""

    repo_url: HttpUrl = Field(..., description="인덱싱할 GitHub 저장소의 URL")


class DeleteDocumentRequest(BaseModel):
    """DELETE /documents 요청 스키마"""

    doc_id_or_prefix: str = Field(..., description="삭제할 doc_id 또는 접두사")


class PromotionRequest(BaseModel):
    suggested_kb_doc_id: str = Field(
        ...,
        description="영구 지식 베이스(KB)에 등록되길 희망하는 이름 (예: hr-policy-v3)",
    )
    note_to_admin: Optional[str] = Field(
        None, description="관리자에게 남기는 메모 (예: v2를 대체합니다)"
    )


class SessionAttachment(BaseModel):
    """
    (거버넌스) GET /admin/pending_attachments 등
    API 응답용 '임시 첨부파일' 스키마
    """

    attachment_id: int
    session_id: str
    user_id: Optional[int]
    file_name: str
    file_path: str
    status: str
    pending_review_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """GET /documents 응답 스키마의 각 항목"""

    doc_id: str
    source_type: Optional[str] = None
    owner_user_id: Optional[int] = None
    permission_groups: List[str]
    created_at: datetime
    last_verified_at: datetime
    promoted_from_attachment_id: Optional[int] = None
    model_config = {"from_attributes": True}


# --- 4. 스케줄러 (Scheduler) 관련 스키마 ---


class TaskCreate(BaseModel):
    task_name: str
    schedule: str
    task_kwargs: dict


class TaskResponse(TaskCreate):
    task_id: int
    user_id: int
    is_active: bool
    model_config = {"from_attributes": True}


# --- 5. 작업 상태 (Task Status) 관련 스키마 ---


class TaskStatusResponse(BaseModel):
    """GET /documents/task-status/{task_id} 응답 스키마"""

    task_id: str
    status: str
    result: Optional[Any] = None


# --- 6. 관리자 (Admin) 관련 스키마 ---


class UpdatePermissionsRequest(BaseModel):
    """PUT /admin/users/{user_id}/permissions 요청 스키마"""

    groups: List[str] = Field(..., description="새롭게 할당할 권한 그룹 목록")


class PromotionApprovalRequest(BaseModel):
    kb_doc_id: str = Field(
        ..., description="영구 KB에 저장될 최종 확정 ID (관리자가 수정 가능)"
    )
    permission_groups: List[str] = Field(
        ..., description="이 문서에 적용할 최종 권한 그룹"
    )


class ToolBase(BaseModel):
    name: str = Field(..., description="도구 이름 (예: jira_create_ticket)")
    description: str = Field(..., description="LLM을 위한 도구 설명")
    api_endpoint_url: HttpUrl = Field(..., description="호출할 API 엔드포인트")
    json_schema: Dict[str, Any] = Field(..., description="인자의 JSON Schema")
    permission_groups: List[str] = Field(default_factory=lambda: ["admin"])
    is_active: bool = True


class ToolCreate(ToolBase):
    pass


class ToolUpdate(ToolBase):
    pass


class ToolResponse(ToolBase):
    tool_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class AdminAuditLog(BaseModel):
    """관리자 감사 로그 응답 스키마"""

    log_id: int
    actor_user_id: int
    action: str
    target_id: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AgentAuditLog(BaseModel):
    """에이전트 감사 로그 응답 스키마"""

    log_id: int
    session_id: Optional[str] = None
    created_at: datetime
    question: str
    permission_groups: Optional[List[str]] = None
    tool_choice: Optional[str] = None
    code_input: Optional[str] = None
    final_answer: Optional[str] = None
    full_agent_state: Dict[str, Any]
    model_config = {"from_attributes": True}
