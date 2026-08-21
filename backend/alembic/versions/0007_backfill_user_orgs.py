"""Backfill: create organisations for users with NULL org_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Find users with NULL org_id who need an organisation
    result = bind.execute(text(
        "SELECT id, email, full_name FROM users WHERE org_id IS NULL"
    ))
    users_without_org = result.fetchall()

    for user in users_without_org:
        user_id, email, full_name = user[0], user[1], user[2]
        org_name = f"Organisation de {full_name or email}"

        # Create org
        org_result = bind.execute(text(
            "INSERT INTO organisations (id, name, plan) "
            "VALUES (gen_random_uuid()::text, :name, 'free') RETURNING id"
        ), {"name": org_name})
        org_id = org_result.fetchone()[0]

        # Update user
        bind.execute(text(
            "UPDATE users SET org_id = :org_id WHERE id = :user_id"
        ), {"org_id": org_id, "user_id": user_id})

        print(f"[0007] Org '{org_name}' créée pour user {email} → org_id={org_id}")


def downgrade() -> None:
    pass  # No safe rollback for this backfill
