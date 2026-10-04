"""Initial Color Rush Live schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

from color_rush.infrastructure.persistence.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
