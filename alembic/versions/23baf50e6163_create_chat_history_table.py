"""create_chat_history_table

Revision ID: 23baf50e6163
Revises: 63047c843d04
Create Date: 2025-11-13 21:01:30.836930

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "23baf50e6163"
down_revision: Union[str, Sequence[str], None] = "63047c843d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 'chat_history' 테이블 생성 ###
    op.create_table(
        "chat_history",
        sa.Column(
            "message_id", sa.BIGINT(), sa.Identity(), nullable=False, primary_key=True
        ),
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.TEXT(), nullable=True, index=True),
        sa.Column(
            "role", sa.VARCHAR(length=20), nullable=False
        ),  # 'user' or 'assistant'
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # ### 'chat_history' 테이블 삭제 ###
    op.drop_table("chat_history")
