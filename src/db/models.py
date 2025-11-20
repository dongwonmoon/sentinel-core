# -*- coding: utf-8 -*-
"""
데이터베이스 테이블에 매핑되는 SQLAlchemy ORM(Object-Relational Mapping) 모델을 정의합니다.

이 파일은 애플리케이션의 전체 데이터 구조를 파이썬 클래스로 표현하는 "데이터 사전" 역할을 합니다.
SQLAlchemy의 선언적 매핑(Declarative Mapping)을 사용하여 각 클래스는 데이터베이스의 테이블에,
클래스의 속성은 테이블의 컬럼에 연결됩니다.

정의된 모델 목록:
- Base: 모든 모델이 상속하는 기본 클래스.
- User: 사용자 정보 및 인증.
- ChatHistory: 모든 채팅 메시지 기록.
- UserProfile: 사용자별 프로필 정보 (LLM 컨텍스트용).
- SessionAttachment: 채팅 세션에 임시로 첨부된 파일.
- SessionAttachmentChunk: 임시 첨부 파일의 분할된 조각과 임베딩.
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
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="메시지 내용"
    )
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
        return f"<SessionAttachmentChunk(id={self.chunk_id}, att_id={self.attachment_id})>"
