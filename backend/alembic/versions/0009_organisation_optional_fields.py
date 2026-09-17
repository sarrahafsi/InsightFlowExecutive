"""Add optional profile fields to organisations (sector, company_size, country, website)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("sector", sa.String(length=100), nullable=True))
    op.add_column("organisations", sa.Column("company_size", sa.String(length=50), nullable=True))
    op.add_column("organisations", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("organisations", sa.Column("website", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "website")
    op.drop_column("organisations", "country")
    op.drop_column("organisations", "company_size")
    op.drop_column("organisations", "sector")
