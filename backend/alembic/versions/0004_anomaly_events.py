"""Add anomaly_events table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "anomaly_events" not in inspector.get_table_names():
        op.create_table(
            "anomaly_events",
            sa.Column("id",             sa.Integer(),    primary_key=True, autoincrement=True),
            sa.Column("user_id",        sa.String(255),  nullable=False, server_default="default"),
            sa.Column("source",         sa.String(50),   nullable=False),
            sa.Column("metric",         sa.String(100),  nullable=False),
            sa.Column("current_value",  sa.Float(),      nullable=False),
            sa.Column("baseline_value", sa.Float(),      nullable=False),
            sa.Column("anomaly_score",  sa.Float(),      nullable=False),
            sa.Column("severity",       sa.String(20),   nullable=False),
            sa.Column("description",    sa.Text(),       nullable=True),
            sa.Column("detected_at",    sa.TIMESTAMP(),  server_default=sa.text("NOW()"), nullable=True),
            sa.Column("window_days",    sa.Integer(),    server_default="7", nullable=True),
            sa.Column("is_read",        sa.Boolean(),    server_default="false", nullable=True),
        )


def downgrade() -> None:
    op.drop_table("anomaly_events")
