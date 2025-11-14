"""create_user_profile_table

Revision ID: 6264e8c7a3a2
Revises: 699564c2aec0
Create Date: 2025-11-14 23:32:27.143600

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6264e8c7a3a2"
down_revision: Union[str, Sequence[str], None] = "699564c2aec0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("profile_text", sa.TEXT(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_profile")
