"""task + task_run + seen_release tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "task",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schedule_cron", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("config_yaml", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column("last_run_accepted", sa.Integer(), nullable=True),
        sa.Column("last_run_considered", sa.Integer(), nullable=True),
    )
    op.create_index("ix_task_name", "task", ["name"], unique=True)

    op.create_table(
        "task_run",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("considered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("log", sa.Text(), nullable=False, server_default=""),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_task_run_task_id", "task_run", ["task_id"])

    op.create_table(
        "seen_release",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column("seen_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    )
    op.create_index("ix_seen_release_task_id", "seen_release", ["task_id"])
    op.create_index("ix_seen_release_key", "seen_release", ["key"])


def downgrade() -> None:
    op.drop_index("ix_seen_release_key", table_name="seen_release")
    op.drop_index("ix_seen_release_task_id", table_name="seen_release")
    op.drop_table("seen_release")
    op.drop_index("ix_task_run_task_id", table_name="task_run")
    op.drop_table("task_run")
    op.drop_index("ix_task_name", table_name="task")
    op.drop_table("task")
