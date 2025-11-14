"""create_admin_audit_log_table

Revision ID: 699564c2aec0
Revises: 23baf50e6163
Create Date: 2025-11-14 23:20:45.175164

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "699564c2aec0"
down_revision: Union[str, Sequence[str], None] = "23baf50e6163"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "log_id", sa.BIGINT(), sa.Identity(), nullable=False, primary_key=True
        ),
        sa.Column(
            "actor_user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "action", sa.VARCHAR(length=255), nullable=False
        ),  # e.g., "update_user_permissions"
        sa.Column(
            "target_id", sa.TEXT(), nullable=True
        ),  # e.g., "user_id: 5" or "doc_id: file.txt"
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("admin_audit_log")
