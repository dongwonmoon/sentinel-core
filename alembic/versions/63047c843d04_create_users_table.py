"""create_users_table

Revision ID: 63047c843d04
Revises: 681f1abceb92
Create Date: 2025-11-13 18:52:55.031483

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "63047c843d04"
down_revision: Union[str, Sequence[str], None] = "681f1abceb92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 'users' 테이블 생성 ###
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "username",
            sa.VARCHAR(length=100),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("hashed_password", sa.TEXT(), nullable=False),
        # [핵심] 사용자의 권한 그룹을 저장할 컬럼
        sa.Column(
            "permission_groups",
            postgresql.ARRAY(sa.TEXT()),
            server_default=sa.text("ARRAY['all_users']"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # ### 'users' 테이블 삭제 ###
    op.drop_table("users")
