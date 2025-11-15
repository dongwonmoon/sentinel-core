"""add_registered_tools_table

Revision ID: cf23a709bd62
Revises: 6eec13c8f3dc
Create Date: 2025-11-16 00:33:27.825959

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "cf23a709bd62"
down_revision: Union[str, Sequence[str], None] = "6eec13c8f3dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "registered_tools",
        sa.Column(
            "tool_id",
            sa.BIGINT(),
            sa.Identity(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "name",
            sa.VARCHAR(length=100),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("api_endpoint_url", sa.TEXT(), nullable=False),
        sa.Column(
            "json_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "permission_groups",
            postgresql.ARRAY(sa.TEXT()),
            server_default=sa.text("ARRAY['admin']"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    # 권한 그룹 검색을 위한 GIN 인덱스
    op.create_index(
        "idx_tools_permission_groups",
        "registered_tools",
        ["permission_groups"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_tools_permission_groups", table_name="registered_tools")
    op.drop_table("registered_tools")
