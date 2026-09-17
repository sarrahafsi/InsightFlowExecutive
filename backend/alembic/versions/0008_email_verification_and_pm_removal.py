"""Add email verification columns to users, backfill role=pm -> ceo

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("verification_token", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("verification_token_expires_at", sa.TIMESTAMP(), nullable=True))

    bind = op.get_bind()
    bind.execute(text("UPDATE users SET role = 'ceo' WHERE role = 'pm'"))


def downgrade() -> None:
    op.drop_column("users", "verification_token_expires_at")
    op.drop_column("users", "verification_token")
    op.drop_column("users", "email_verified")
