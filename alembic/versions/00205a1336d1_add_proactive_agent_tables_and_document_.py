"""add_proactive_agent_tables_and_document_ownership

Revision ID: 00205a1336d1
Revises: c7bf1f308d4b
Create Date: 2025-11-15 08:57:04.348589

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "00205a1336d1"
down_revision: Union[str, Sequence[str], None] = "c7bf1f308d4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 1. [P2.4] 'documents' 테이블에 소유권 및 검증일 추가 ###
    op.add_column(
        "documents",
        sa.Column(
            "owner_user_id",
            sa.BIGINT(),
            sa.ForeignKey(
                "users.user_id", ondelete="SET NULL"
            ),  # 소유자가 탈퇴해도 문서는 남김
            nullable=True,
            index=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "last_verified_at",
            sa.TIMESTAMP(),
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),  # 생성 시 현재 시간으로 설정
            nullable=True,
        ),
    )

    # ### 2. [P2.1] 'scheduled_tasks' 테이블 생성 ###
    op.create_table(
        "scheduled_tasks",
        sa.Column(
            "task_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "task_name", sa.VARCHAR(length=255), nullable=False
        ),  # e.g., "daily_github_summary"
        sa.Column(
            "schedule", sa.VARCHAR(length=100), nullable=False
        ),  # e.g., "0 9 * * *" (crontab)
        sa.Column(
            "task_kwargs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),  # e.g., {"repo_url": "..."}
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )

    # ### 3. [P2.1] 'user_notifications' 테이블 생성 ###
    op.create_table(
        "user_notifications",
        sa.Column(
            "notification_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BIGINT(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("message", sa.TEXT(), nullable=False),
        sa.Column(
            "is_read",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_notifications")
    op.drop_table("scheduled_tasks")
    op.drop_column("documents", "last_verified_at")
    op.drop_column("documents", "owner_user_id")
