"""Add status and progress to projects + decision_log table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Add columns to projects only if they don't exist
    existing = [c["name"] for c in inspector.get_columns("projects")]
    if "status" not in existing:
        op.add_column("projects", sa.Column("status",     sa.String(20),    server_default="on_track", nullable=True))
    if "progress" not in existing:
        op.add_column("projects", sa.Column("progress",   sa.SmallInteger(), server_default="0",        nullable=True))
    if "blockers" not in existing:
        op.add_column("projects", sa.Column("blockers",   sa.SmallInteger(), server_default="0",        nullable=True))
    if "risk_level" not in existing:
        op.add_column("projects", sa.Column("risk_level", sa.String(20),    server_default="Low",      nullable=True))
    if "sentiment" not in existing:
        op.add_column("projects", sa.Column("sentiment",  sa.String(20),    server_default="Neutral",  nullable=True))

    # Create decision_log only if it doesn't exist
    if "decision_log" not in inspector.get_table_names():
        op.create_table(
            "decision_log",
            sa.Column("id",         sa.Integer(),   primary_key=True, autoincrement=True),
            sa.Column("title",      sa.Text(),      nullable=False),
            sa.Column("context",    sa.Text(),      nullable=True),
            sa.Column("status",     sa.String(20),  server_default="pending", nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()"), nullable=True),
            sa.Column("decided_at", sa.TIMESTAMP(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("projects", "status")
    op.drop_column("projects", "progress")
    op.drop_table("decision_log")
