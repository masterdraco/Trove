"""app_setting key/value table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column(
            "key", sqlmodel.sql.sqltypes.AutoString(length=128), primary_key=True, nullable=False
        ),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(length=4096), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
