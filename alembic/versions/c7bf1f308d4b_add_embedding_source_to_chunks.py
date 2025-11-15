"""add_embedding_source_to_chunks

Revision ID: c7bf1f308d4b
Revises: 6264e8c7a3a2
Create Date: 2025-11-15 08:37:09.209675

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7bf1f308d4b"
down_revision: Union[str, Sequence[str], None] = "6264e8c7a3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_source_text",  # 임베딩에 실제 사용된 텍스트 (e.g., 가상 질문)
            sa.TEXT(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding_source_text")
