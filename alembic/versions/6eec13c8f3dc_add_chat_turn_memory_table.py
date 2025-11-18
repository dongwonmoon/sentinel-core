"""add_chat_turn_memory_table

Revision ID: 6eec13c8f3dc
Revises: 00205a1336d1
Create Date: 2025-11-15 21:40:10.612765

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6eec13c8f3dc"
down_revision: Union[str, Sequence[str], None] = "c7bf1f308d4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 'chat_turn_memory' 테이블 생성
    op.create_table(
        "chat_turn_memory",
        sa.Column(
            "turn_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("session_id", sa.TEXT(), nullable=False, index=True),
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("turn_text", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )

    # 2. 'embedding' 벡터 컬럼 추가 (pgvector)
    # (nomic-embed-text의 차원인 768로 가정, 다를 경우 수정 필요)
    op.execute("ALTER TABLE chat_turn_memory ADD COLUMN embedding vector(768)")

    # 3. 벡터 인덱스 생성 (HNSW)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_turn_memory_embedding_hnsw 
        ON chat_turn_memory 
        USING hnsw (embedding vector_l2_ops);
    """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_turn_memory_embedding_hnsw;")
    op.drop_table("chat_turn_memory")
