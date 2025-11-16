"""add_governance_session_attachment_tables

Revision ID: b30a29421e50
Revises: cf23a709bd62
Create Date: 2025-11-16 09:39:47.671252

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b30a29421e50"
down_revision: Union[str, Sequence[str], None] = "cf23a709bd62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 'session_attachments' 테이블 생성
    op.create_table(
        "session_attachments",
        sa.Column(
            "attachment_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("session_id", sa.TEXT(), nullable=False, index=True),
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("file_name", sa.TEXT(), nullable=False),
        sa.Column("file_path", sa.TEXT(), nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(length=50),
            server_default="indexing",
            nullable=False,
        ),
        sa.Column(
            "pending_review_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )

    # 2. 'session_attachment_chunks' 테이블 생성
    op.create_table(
        "session_attachment_chunks",
        sa.Column(
            "chunk_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "attachment_id",
            sa.BIGINT(),
            sa.ForeignKey("session_attachments.attachment_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_text", sa.TEXT(), nullable=False),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 3. 'session_attachment_chunks'에 벡터 컬럼 추가 (예: 768 차원)
    op.execute("ALTER TABLE session_attachment_chunks ADD COLUMN embedding vector(768)")

    # 4. 'session_attachment_chunks'에 벡터 인덱스 생성
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_session_chunks_embedding_hnsw
        ON session_attachment_chunks
        USING hnsw (embedding vector_l2_ops);
    """
    )

    # 5. 'documents' 테이블에 '승격' 추적 컬럼 추가
    op.add_column(
        "documents",
        sa.Column(
            "promoted_from_attachment_id",
            sa.BIGINT(),
            sa.ForeignKey("session_attachments.attachment_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    # 역순으로 삭제
    op.drop_column("documents", "promoted_from_attachment_id")

    op.execute("DROP INDEX IF EXISTS idx_session_chunks_embedding_hnsw;")
    op.drop_table("session_attachment_chunks")

    op.drop_table("session_attachments")
