# -*- coding: utf-8 -*-
"""
데이터베이스 테이블에 매핑되는 SQLAlchemy ORM(Object-Relational Mapping) 모델을 정의합니다.

이 파일은 애플리케이션의 전체 데이터 구조를 파이썬 클래스로 표현하는 "데이터 사전" 역할을 합니다.
SQLAlchemy의 선언적 매핑(Declarative Mapping)을 사용하여 각 클래스는 데이터베이스의 테이블에,
클래스의 속성은 테이블의 컬럼에 연결됩니다.

정의된 모델 목록:
- Base: 모든 모델이 상속하는 기본 클래스.
- User: 사용자 정보 및 인증.
- Document: 영구 지식베이스(KB)에 저장된 문서의 메타 정보.
- DocumentChunk: 분할된 영구 문서 조각과 그 임베딩 벡터.
- ChatHistory: 모든 채팅 메시지 기록.
- UserProfile: 사용자별 프로필 정보 (LLM 컨텍스트용).
- AgentAuditLog: 에이전트의 작동 과정을 기록하는 감사 로그.
- ChatTurnMemory: '사건 기억'을 위한 대화 턴 단위의 임베딩.
- SessionAttachment: (거버넌스) 채팅 세션에 임시로 첨부된 파일.
- SessionAttachmentChunk: (거버넌스) 임시 첨부 파일의 분할된 조각과 임베딩.
- RegisteredTool: (동적 도구) 관리자가 등록한 외부 API 기반 도구.
"""

import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    BIGINT,
    BOOLEAN,
    TIMESTAMP,
    ForeignKey,
    Identity,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """
    모든 ORM 모델의 기본이 되는 선언적 기본 클래스입니다.
    공통적인 타입 어노테이션 설정 등을 포함할 수 있습니다.
    """

    # PostgreSQL의 JSONB 타입을 파이썬의 dict 타입과 매핑하기 위한 설정
    type_annotation_map = {
        Dict[str, any]: JSONB,
    }


# ==============================================================================
# 1. 사용자 및 인증 관련 모델
# ==============================================================================


class User(Base):
    """
    'users' 테이블: 애플리케이션의 사용자 정보를 관리합니다.

    이 모델은 사용자 인증(로그인)의 기반이 되며, 각 사용자가 어떤 권한 그룹에
    속하는지를 정의하여 데이터 접근 제어(RAG 등)에 사용됩니다.
    """

    __tablename__ = "users"

    # --- 컬럼 정의 ---
    user_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="사용자 고유 ID (PK, 자동 증가)",
    )
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="사용자 이름 (로그인 시 사용, 고유값)",
    )
    hashed_password: Mapped[str] = mapped_column(
        Text, nullable=False, comment="해시 처리된 비밀번호"
    )
    permission_groups: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        server_default=func.text("ARRAY['all_users']"),
        nullable=False,
        comment="사용자가 속한 권한 그룹 목록 (RAG 문서 접근 제어에 사용)",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="계정 생성일 (UTC)",
    )
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=func.text("true"),
        nullable=False,
        comment="계정 활성화 여부 (비활성화 시 로그인 불가)",
    )

    # --- 관계(Relationship) 정의 ---
    # `back_populates`는 양방향 관계를 설정하여, 양쪽 객체에서 서로를 참조할 수 있게 합니다.
    # `cascade="all, delete-orphan"`: User가 삭제될 때, 관련된 모든 자식 객체도 함께 삭제되도록 합니다.

    # User -> ChatHistory (1:N 관계)
    chat_messages: Mapped[List["ChatHistory"]] = relationship(
        "ChatHistory", back_populates="user", cascade="all, delete-orphan"
    )
    # User -> UserProfile (1:1 관계)
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    # User -> Document (1:N 관계)
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.user_id}, username='{self.username}')>"


class UserProfile(Base):
    """
    'user_profile' 테이블: LLM에 컨텍스트로 제공될 수 있는 사용자별 프로필 정보를 저장합니다.

    이 정보는 에이전트가 사용자의 역할, 선호도 등을 파악하여 더 개인화된 답변을
    생성하는 데 사용될 수 있습니다. User와 1:1 관계를 가집니다.
    """

    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="프로필 소유 사용자의 ID (PK, FK to users.user_id)",
    )
    profile_text: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="사용자 프로필 내용 (예: '나는 파이썬 백엔드 개발자입니다.')",
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="마지막 프로필 업데이트 시간 (UTC)",
    )

    # UserProfile -> User (1:1 관계)
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id})>"


# ==============================================================================
# 2. 영구 지식베이스(Permanent KB) 관련 모델 (RAG의 핵심)
# ==============================================================================


class Document(Base):
    """
    'documents' 테이블: 업로드되어 '영구 지식'으로 등록된 문서의 메타데이터를 관리합니다.

    하나의 문서는 여러 개의 청크(DocumentChunk)로 분할되어 저장됩니다.
    이 테이블은 각 문서의 소유자, 접근 권한 등을 정의합니다.
    """

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        comment="문서의 고유 식별자 (PK, 예: 파일 경로, URL)",
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="문서 출처 유형 (예: 'file', 'github-repo', 'web')",
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
        comment="문서를 업로드한 사용자 ID (FK to users.user_id)",
    )
    permission_groups: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="이 문서에 접근할 수 있는 권한 그룹 목록 (RAG 접근 제어의 핵심)",
    )
    extra_metadata: Mapped[Dict[str, any]] = mapped_column(
        JSONB, nullable=True, comment="추가적인 메타데이터 (JSONB 형식)"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="문서 생성일 (UTC)",
    )
    last_verified_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="문서의 유효성이 마지막으로 확인된 시간 (주기적인 동기화에 사용)",
    )
    # (거버넌스) 어떤 임시 파일로부터 승격되었는지 추적
    promoted_from_attachment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("session_attachments.attachment_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="이 지식이 승격된 원본 임시 첨부파일 ID (FK to session_attachments.attachment_id)",
    )

    # --- 관계(Relationship) 정의 ---
    # Document -> User (N:1 관계)
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    # Document -> DocumentChunk (1:N 관계)
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )
    # Document -> SessionAttachment (1:1 관계, 추적용)
    promoted_from: Mapped["SessionAttachment"] = relationship(
        "SessionAttachment", foreign_keys=[promoted_from_attachment_id]
    )

    def __repr__(self) -> str:
        return f"<Document(doc_id='{self.doc_id}')>"


class DocumentChunk(Base):
    """
    'document_chunks' 테이블: 분할된 '영구' 문서의 각 조각(청크)과 임베딩 벡터를 저장합니다.

    이 테이블은 벡터 검색의 핵심 대상으로, RAG 과정에서 유사도 검색이 수행되는 주체입니다.
    """

    __tablename__ = "document_chunks"

    chunk_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="청크의 고유 ID (PK, 자동 증가)",
    )
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="부모 문서의 ID (FK to documents.doc_id, 부모 삭제 시 함께 삭제)",
    )
    chunk_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="분할된 문서 조각의 원본 텍스트 내용"
    )
    embedding: Mapped[List[float]] = mapped_column(
        "embedding",
        Vector(768),  # 하드코딩 주의
        nullable=False,
        comment="텍스트에 대한 벡터 임베딩 (pgvector 타입)",
    )
    extra_metadata: Mapped[Dict[str, any]] = mapped_column(
        JSONB, nullable=True, comment="청크 관련 추가 메타데이터 (JSONB 형식)"
    )

    # --- 관계(Relationship) 정의 ---
    # DocumentChunk -> Document (N:1 관계)
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk(chunk_id={self.chunk_id}, doc_id='{self.doc_id}')>"


# ==============================================================================
# 3. 채팅 및 메모리 관련 모델
# ==============================================================================


class ChatHistory(Base):
    """
    'chat_history' 테이블: 모든 사용자의 채팅 메시지를 순서대로 저장합니다.

    '단기 기억(Short-term memory)'을 구현하는 데 사용되며, 대화의 흐름을
    파악하기 위한 기본 컨텍스트를 제공합니다.
    """

    __tablename__ = "chat_history"

    message_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="메시지 고유 ID (PK, 자동 증가)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="메시지를 작성한 사용자 ID (FK to users.user_id)",
    )
    session_id: Mapped[str] = mapped_column(
        Text,
        index=True,
        nullable=True,
        comment="채팅 세션 ID. 동일한 대화를 그룹화하는 데 사용됩니다.",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="메시지 작성자 역할 ('user' 또는 'assistant')",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="메시지 내용")
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="메시지 생성 시간 (UTC)",
    )

    # --- 관계(Relationship) 정의 ---
    # ChatHistory -> User (N:1 관계)
    user: Mapped["User"] = relationship("User", back_populates="chat_messages")

    def __repr__(self) -> str:
        return f"<ChatHistory(id={self.message_id}, role='{self.role}')>"


class ChatTurnMemory(Base):
    """
    'chat_turn_memory' 테이블: '사건 기억(Episodic Memory)'을 위한 벡터 테이블입니다.

    각 대화 턴(사용자 질문 + AI 답변)의 원본 텍스트와 임베딩을 저장하여,
    과거의 특정 '사건'(예: 특정 코드 수정, 특정 주제에 대한 논의)을
    현재 질문과 관련하여 RAG로 인출(retrieve)하는 데 사용됩니다.
    """

    __tablename__ = "chat_turn_memory"

    turn_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="대화 턴의 고유 ID (PK, 자동 증가)",
    )
    session_id: Mapped[str] = mapped_column(
        Text,
        index=True,
        nullable=False,
        comment="관련 채팅 세션 ID",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="사용자 ID (FK to users.user_id)",
    )
    turn_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="해당 턴의 전체 텍스트 (User 질문 + AI 답변)",
    )
    embedding: Mapped[List[float]] = mapped_column(
        "embedding",
        Vector(768),  # 하드코딩 주의
        nullable=False,
        comment="turn_text에 대한 벡터 임베딩",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="메시지 생성 시간 (UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<ChatTurnMemory(turn_id={self.turn_id}, session_id='{self.session_id}')>"
        )


# ==============================================================================
# 4. (거버넌스) 임시 세션 첨부파일 관련 모델
# ==============================================================================


class SessionAttachment(Base):
    """
    'session_attachments' 테이블: 사용자가 채팅 세션에 '임시'로 첨부한 파일을 관리합니다.

    이 모델은 '듀얼 RAG'의 한 축인 'Session KB'를 구성하며, 파일의 상태
    (인덱싱 중, 임시, 승격 검토 중 등)를 추적하는 거버넌스 워크플로우의 첫 단계입니다.
    """

    __tablename__ = "session_attachments"

    attachment_id: Mapped[int] = mapped_column(
        BIGINT, Identity(), primary_key=True, comment="첨부파일 고유 ID (PK)"
    )
    session_id: Mapped[str] = mapped_column(
        Text, index=True, nullable=False, comment="이 파일이 첨부된 세션 ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        index=True,
        nullable=True,  # 소유자가 탈퇴해도 파일은 남을 수 있음
        comment="첨부한 사용자 ID (FK to users.user_id)",
    )
    file_name: Mapped[str] = mapped_column(
        Text, nullable=False, comment="원본 파일 이름"
    )
    file_path: Mapped[str] = mapped_column(
        Text, nullable=False, comment="저장된 경로 (예: S3 키 또는 로컬 경로)"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="indexing",
        comment="파일 상태: indexing, temporary, pending_review, promoted, rejected, failed",
    )
    pending_review_metadata: Mapped[Optional[Dict[str, any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="영구 지식으로 승격 요청 시 사용자가 제출한 메타데이터 (대상 KB, 권한 그룹 등)",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )

    # --- 관계(Relationship) 정의 ---
    # SessionAttachment -> User (N:1 관계)
    user: Mapped["User"] = relationship()
    # SessionAttachment -> SessionAttachmentChunk (1:N 관계)
    chunks: Mapped[List["SessionAttachmentChunk"]] = relationship(
        "SessionAttachmentChunk",
        back_populates="attachment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SessionAttachment(id={self.attachment_id}, name='{self.file_name}')>"


class SessionAttachmentChunk(Base):
    """
    'session_attachment_chunks' 테이블: '임시' 첨부파일의 청크와 임베딩을 저장합니다.

    이 테이블은 '듀얼 RAG'에서 현재 세션에만 한정된 정보를 검색하는 데 사용되는
    'Session KB'의 벡터 저장소 역할을 합니다.
    """

    __tablename__ = "session_attachment_chunks"

    chunk_id: Mapped[int] = mapped_column(
        BIGINT, Identity(), primary_key=True, comment="임시 청크의 고유 ID (PK)"
    )
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("session_attachments.attachment_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="부모 첨부파일의 ID (FK to session_attachments.attachment_id)",
    )
    chunk_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="분할된 조각의 텍스트"
    )
    embedding: Mapped[List[float]] = mapped_column(
        "embedding",
        Vector(768),  # 하드코딩 주의
        nullable=False,
        comment="텍스트에 대한 벡터 임베딩 (pgvector 타입)",
    )
    extra_metadata: Mapped[Dict[str, any]] = mapped_column(
        JSONB, nullable=True, comment="청크 관련 추가 메타데이터 (JSONB 형식)"
    )

    # --- 관계(Relationship) 정의 ---
    # SessionAttachmentChunk -> SessionAttachment (N:1 관계)
    attachment: Mapped["SessionAttachment"] = relationship(
        "SessionAttachment", back_populates="chunks"
    )

    def __repr__(self) -> str:
        return (
            f"<SessionAttachmentChunk(id={self.chunk_id}, att_id={self.attachment_id})>"
        )


# ==============================================================================
# 5. 에이전트 기능 확장 관련 모델
# ==============================================================================


class RegisteredTool(Base):
    """
    'registered_tools' 테이블: '동적 도구 레지스트리' 역할을 합니다.

    관리자가 등록한 외부 API 기반 도구(플러그인) 정보를 저장합니다. 에이전트는
    이 테이블을 동적으로 쿼리하여, 사용자 권한에 맞는 사용 가능한 도구 목록을
    실시간으로 구성합니다. 이를 통해 코드 변경 없이 에이전트의 능력을 확장할 수 있습니다.
    """

    __tablename__ = "registered_tools"

    tool_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="도구 고유 ID (PK, 자동 증가)",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="도구의 고유 이름 (LLM이 호출할 이름, 예: 'jira_create_ticket')",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="LLM이 도구의 기능과 사용법을 이해하기 위한 상세 설명",
    )
    api_endpoint_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="도구가 호출할 API 엔드포인트의 전체 URL",
    )
    json_schema: Mapped[Dict[str, any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="도구 호출에 필요한 인자(argument)의 JSON Schema. 예: {'type': 'object', 'properties': {'summary': {'type': 'string'}}}",
    )
    permission_groups: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=sa.text("ARRAY['admin']"),  # 기본값: admin만 사용 가능
        comment="이 도구를 사용할 수 있는 권한 그룹 목록",
    )
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=sa.text("true"),
        nullable=False,
        comment="도구 활성화 여부",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="도구 등록일 (UTC)",
    )

    def __repr__(self) -> str:
        return f"<RegisteredTool(tool_id={self.tool_id}, name='{self.name}')>"


class AgentAuditLog(Base):
    """
    'agent_audit_log' 테이블: 에이전트의 모든 요청 처리 과정을 기록합니다.

    디버깅, 성능 분석, 사용 패턴 파악 등 운영 및 분석 목적으로 사용됩니다.
    LangGraph의 최종 상태를 JSON으로 저장하여, 특정 요청에 대한 에이전트의
    전체 '생각의 흐름'을 사후에 재구성하고 분석할 수 있습니다.
    """

    __tablename__ = "agent_audit_log"

    log_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="로그 고유 ID (PK, 자동 증가)",
    )
    session_id: Mapped[str] = mapped_column(
        Text, index=True, nullable=True, comment="관련된 채팅 세션 ID"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.current_timestamp(),
        comment="로그 생성 시간 (UTC)",
    )
    # --- 에이전트의 주요 입력값 ---
    question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="사용자의 원본 질문"
    )
    permission_groups: Mapped[List[str]] = mapped_column(
        ARRAY(Text), nullable=True, comment="요청 시점의 사용자 권한 그룹"
    )
    # --- 에이전트의 중간 결정 및 결과 ---
    tool_choice: Mapped[str] = mapped_column(
        String(100), nullable=True, comment="라우터가 결정한 도구 이름"
    )
    code_input: Mapped[str] = mapped_column(
        Text, nullable=True, comment="코드 실행 도구가 생성/사용한 코드"
    )
    final_answer: Mapped[str] = mapped_column(
        Text, nullable=True, comment="에이전트가 생성한 최종 답변"
    )
    # --- 전체 상태 (디버깅용) ---
    full_agent_state: Mapped[Dict[str, any]] = mapped_column(
        JSONB,
        server_default=func.text("'{}'::jsonb"),
        comment="디버깅을 위한 LangGraph의 전체 최종 상태 (JSONB 형식)",
    )

    def __repr__(self) -> str:
        return f"<AgentAuditLog(id={self.log_id}, session_id='{self.session_id}')>"
