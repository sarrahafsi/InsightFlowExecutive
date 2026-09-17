"""Encrypt source_configs.config at rest (OAuth tokens / API keys)

source_configs.config held Gmail/Outlook/Teams/Jira/... tokens as plaintext
JSONB — readable by anyone with DB access (a leaked backup, an overprivileged
DB role, etc). It's now Fernet-encrypted text via core.models.EncryptedJSON,
keyed by TOKEN_ENCRYPTION_KEY (must be set in the environment before this runs
— see core/config.py).

Existing rows are plaintext and cannot be retroactively encrypted in SQL, so
this migration clears them: every connected source needs to be reconnected
once after deploying. There is nothing else to migrate — access/refresh
tokens are short-lived and org-scoped, not data you'd want to preserve
un-encrypted anyway.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM source_configs")
    op.alter_column(
        "source_configs", "config",
        type_=sa.Text(),
        postgresql_using="config::text",
        nullable=False,
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_configs")
    op.alter_column(
        "source_configs", "config",
        type_=JSONB(astext_type=sa.Text()),
        postgresql_using="config::jsonb",
        nullable=False,
    )
