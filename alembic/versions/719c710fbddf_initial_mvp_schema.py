"""initial_mvp_schema

Revision ID: 719c710fbddf
Revises:
Create Date: 2025-11-20 10:52:21.124928

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

# revision identifiers, used by Alembic.
revision: str = "719c710fbddf"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. [필수] pgvector 확장 활성화
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. users 테이블 (권한 그룹 제거됨)
    op.create_table(
        "users",
        sa.Column("user_id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 3. user_profile 테이블 (사용자 설정/정보)
    op.create_table(
        "user_profile",
        sa.Column("user_id", sa.BIGINT(), primary_key=True),
        sa.Column("profile_text", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
    )

    # 4. chat_history 테이블 (단기 기억)
    op.create_table(
        "chat_history",
        sa.Column("message_id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),  # user, assistant
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_chat_history_session_id", "chat_history", ["session_id"]
    )
    op.create_index("ix_chat_history_user_id", "chat_history", ["user_id"])

    # 5. session_attachments 테이블 (세션 파일 관리)
    op.create_table(
        "session_attachments",
        sa.Column(
            "attachment_id", sa.BIGINT(), sa.Identity(), primary_key=True
        ),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.BIGINT(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),  # 로컬 경로 또는 URL
        sa.Column(
            "status", sa.String(50), server_default="indexing", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_session_attachments_session_id",
        "session_attachments",
        ["session_id"],
    )

    # 6. session_attachment_chunks 테이블 (벡터 저장소)
    op.create_table(
        "session_attachment_chunks",
        sa.Column("chunk_id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("attachment_id", sa.BIGINT(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column(
            "embedding", sa.types.UserDefinedType(), nullable=False
        ),  # Vector 타입
        sa.Column(
            "extra_metadata", sa.dialects.postgresql.JSONB(), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["session_attachments.attachment_id"],
            ondelete="CASCADE",
        ),
    )
    # 벡터 컬럼 정의 (UserDefinedType 우회)
    op.execute(
        "ALTER TABLE session_attachment_chunks ALTER COLUMN embedding TYPE vector(768)"
    )

    # HNSW 인덱스 생성 (벡터 검색 속도 최적화)
    op.execute(
        """
        CREATE INDEX ix_session_chunks_embedding_hnsw 
        ON session_attachment_chunks 
        USING hnsw (embedding vector_l2_ops)
    """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_session_chunks_embedding_hnsw")
    op.drop_table("session_attachment_chunks")
    op.drop_table("session_attachments")
    op.drop_table("chat_history")
    op.drop_table("user_profile")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
