"""Add contributes_to_shared_training consent flag to organisations

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("contributes_to_shared_training", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("organisations", "contributes_to_shared_training", server_default=None)


def downgrade() -> None:
    op.drop_column("organisations", "contributes_to_shared_training")
