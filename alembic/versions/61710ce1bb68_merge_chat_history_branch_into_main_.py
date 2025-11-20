"""Merge chat_history branch into main timeline

Revision ID: 61710ce1bb68
Revises: b30a29421e50, 23baf50e6163
Create Date: 2025-11-17 19:44:39.417446

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "61710ce1bb68"
down_revision: Union[str, Sequence[str], None] = (
    "b30a29421e50",
    "23baf50e6163",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
