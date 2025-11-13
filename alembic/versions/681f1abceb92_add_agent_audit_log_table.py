"""add_agent_audit_log_table

Revision ID: 681f1abceb92
Revises: 711d0b8478e2
Create Date: 2025-11-13 16:00:50.394187

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "681f1abceb92"
down_revision: Union[str, Sequence[str], None] = "711d0b8478e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 'agent_audit_log' 테이블 생성 ###
    op.create_table(
        "agent_audit_log",
        sa.Column(
            "log_id", sa.BIGINT(), sa.Identity(), nullable=False, primary_key=True
        ),
        sa.Column(
            "session_id", sa.TEXT(), nullable=True, index=True
        ),  # 세션/사용자 구분을 위함
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        # --- AgentState의 주요 입력값 ---
        sa.Column("question", sa.TEXT(), nullable=False),
        sa.Column("permission_groups", postgresql.ARRAY(sa.TEXT()), nullable=True),
        # --- AgentBrain의 중간 결정값 ---
        sa.Column("tool_choice", sa.VARCHAR(length=100), nullable=True),
        sa.Column("code_input", sa.TEXT(), nullable=True),
        # --- AgentBrain의 최종 결과값 ---
        sa.Column("final_answer", sa.TEXT(), nullable=True),
        # --- 디버깅 및 전체 추적을 위한 원본 데이터 ---
        sa.Column(
            "full_agent_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # ### 'agent_audit_log' 테이블 삭제 ###
    op.drop_table("agent_audit_log")
