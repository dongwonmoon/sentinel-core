# -*- coding: utf-8 -*-
"""
데이터베이스 테이블에 매핑되는 SQLAlchemy ORM(Object-Relational Mapping) 모델을 정의합니다.

이 파일은 애플리케이션의 데이터 구조를 파이썬 클래스로 표현합니다.
SQLAlchemy의 선언적 매핑(Declarative Mapping)을 사용하여 각 클래스는 데이터베이스의 테이블에,
클래스의 속성은 테이블의 컬럼에 연결됩니다.

- Base: 모든 모델이 상속하는 기본 클래스. 공통 설정을 제공합니다.
- User: 사용자 정보.
- Document: 업로드된 문서의 메타 정보.
- DocumentChunk: 분할된 문서 조각과 그 임베딩 벡터.
- ChatHistory: 채팅 메시지 기록.
- UserProfile: 사용자 프로필 정보.
- AgentAuditLog: 에이전트의 작동 감사 로그.
"""

import datetime
from typing import List, Dict

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


class Base(DeclarativeBase):
    """
    모든 ORM 모델의 기본이 되는 선언적 기본 클래스입니다.
    공통적인 타입 어노테이션 설정 등을 포함할 수 있습니다.
    """

    # PostgreSQL의 JSONB 타입을 파이썬의 dict 타입과 매핑하기 위한 설정
    type_annotation_map = {
        Dict[str, any]: JSONB,
    }


class User(Base):
    """
    'users' 테이블에 매핑되는 ORM 모델.
    애플리케이션의 사용자 정보를 관리합니다.
    """

    __tablename__ = "users"

    # --- 컬럼 정의 ---
    user_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="사용자 고유 ID (자동 증가)",
    )
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="사용자 이름 (로그인 시 사용)",
    )
    hashed_password: Mapped[str] = mapped_column(
        Text, nullable=False, comment="해시된 비밀번호"
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
        comment="계정 활성화 여부",
    )

    # --- 관계(Relationship) 정의 ---
    # 'User' 모델과 다른 모델 간의 관계를 설정합니다.
    # `back_populates`는 양방향 관계를 설정하여, 양쪽 객체에서 서로를 참조할 수 있게 합니다.
    # `cascade="all, delete-orphan"`: User가 삭제될 때, 관련된 모든 자식 객체(채팅 메시지, 프로필 등)도 함께 삭제되도록 합니다.

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


class Document(Base):
    """
    'documents' 테이블에 매핑되는 ORM 모델.
    업로드된 각 문서의 메타데이터와 권한 정보를 관리합니다.
    하나의 문서는 여러 개의 청크(DocumentChunk)를 가질 수 있습니다.
    """

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        comment="문서의 고유 식별자 (예: 파일 경로, URL)",
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="문서 출처 유형 (예: 'file', 'github')",
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
        comment="문서를 업로드한 사용자 ID",
    )
    permission_groups: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="이 문서에 접근할 수 있는 권한 그룹 목록",
    )
    extra_metadata: Mapped[Dict[str, any]] = mapped_column(
        JSONB, nullable=True, comment="추가적인 메타데이터 (JSONB)"
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
        comment="문서의 유효성이 마지막으로 확인된 시간",
    )

    # Document -> User (N:1 관계)
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    # Document -> DocumentChunk (1:N 관계)
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document(doc_id='{self.doc_id}')>"


class DocumentChunk(Base):
    """
    'document_chunks' 테이블에 매핑되는 ORM 모델.
    분할된 문서의 각 조각(청크)과 그에 해당하는 임베딩 벡터를 저장합니다.
    """

    __tablename__ = "document_chunks"

    chunk_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="청크의 고유 ID (자동 증가)",
    )
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="부모 문서의 ID. Document 테이블의 외래 키.",
    )
    chunk_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="분할된 문서 조각의 텍스트 내용"
    )
    embedding: Mapped[List[float]] = mapped_column(
        "embedding",
        Text,
        nullable=False,
        comment="텍스트에 대한 벡터 임베딩 (pgvector 타입)",
    )
    extra_etadata: Mapped[Dict[str, any]] = mapped_column(
        JSONB, nullable=True, comment="청크 관련 추가 메타데이터 (JSONB)"
    )

    # DocumentChunk -> Document (N:1 관계)
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk(chunk_id={self.chunk_id}, doc_id='{self.doc_id}')>"


class ChatHistory(Base):
    """
    'chat_history' 테이블에 매핑되는 ORM 모델.
    모든 사용자의 채팅 메시지를 저장합니다.
    """

    __tablename__ = "chat_history"

    message_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="메시지 고유 ID (자동 증가)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="메시지를 작성한 사용자의 ID. User 테이블의 외래 키.",
    )
    session_id: Mapped[str] = mapped_column(
        Text,
        index=True,
        nullable=True,
        comment="채팅 세션 ID. 동일한 대화를 그룹화합니다.",
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

    # ChatHistory -> User (N:1 관계)
    user: Mapped["User"] = relationship("User", back_populates="chat_messages")

    def __repr__(self) -> str:
        return f"<ChatHistory(id={self.message_id}, role='{self.role}')>"


class UserProfile(Base):
    """
    'user_profile' 테이블에 매핑되는 ORM 모델.
    LLM에 컨텍스트로 제공될 수 있는 사용자별 프로필 정보를 저장합니다.
    """

    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="프로필 소유 사용자의 ID. User 테이블의 외래 키이자 이 테이블의 기본 키.",
    )
    profile_text: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="사용자 프로필 내용 (예: '나는 파이썬 개발자입니다.')",
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


class AgentAuditLog(Base):
    """
    'agent_audit_log' 테이블에 매핑되는 ORM 모델.
    에이전트의 모든 요청 처리 과정을 디버깅 및 분석 목적으로 기록합니다.
    """

    __tablename__ = "agent_audit_log"

    log_id: Mapped[int] = mapped_column(
        BIGINT, Identity(), primary_key=True, comment="로그 고유 ID (자동 증가)"
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


class ChatTurnMemory(Base):
    """
    '사건 기억'을 위한 벡터 테이블
    각 대화 턴(사용자+AI)의 원본 텍스트와 임베딩을 저장하여
    과거의 특정 '사건'(예: 코드 수정)을 RAG로 인출(retrieve)하는 데 사용됩니다.
    """

    __tablename__ = "chat_turn_memory"

    turn_id: Mapped[int] = mapped_column(
        BIGINT,
        Identity(),
        primary_key=True,
        comment="대화 턴의 고유 ID (자동 증가)",
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
        comment="사용자 ID. User 테이블의 외래 키.",
    )
    turn_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="해당 턴의 전체 텍스트 (User + AI)"
    )
    embedding: Mapped[List[float]] = mapped_column(
        "embedding",
        Text,  # pgvector 타입 (alembic에서 vector(dim)으로 명시)
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
