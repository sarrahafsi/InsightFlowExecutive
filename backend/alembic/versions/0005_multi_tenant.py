"""Multi-tenant: add organisations table + org_id on all tables + rename roles

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ── 1. Create organisations table ─────────────────────────────────────────
    if "organisations" not in tables:
        op.create_table(
            "organisations",
            sa.Column("id",         sa.String(36),  primary_key=True),
            sa.Column("name",       sa.String(255), nullable=False),
            sa.Column("plan",       sa.String(50),  server_default="free"),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
        )

    # ── 2. Add org_id to users ────────────────────────────────────────────────
    user_cols = [c["name"] for c in inspector.get_columns("users")]
    if "org_id" not in user_cols:
        op.add_column("users", sa.Column("org_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_users_org", "users", "organisations", ["org_id"], ["id"], ondelete="SET NULL")

    # ── 3. Rename roles: owner→ceo, manager→pm, analyst→pm ───────────────────
    op.execute("UPDATE users SET role = 'ceo' WHERE role = 'owner'")
    op.execute("UPDATE users SET role = 'pm'  WHERE role IN ('manager', 'analyst')")

    # ── 4. Add org_id to messages_raw ────────────────────────────────────────
    msg_cols = [c["name"] for c in inspector.get_columns("messages_raw")]
    if "org_id" not in msg_cols:
        op.add_column("messages_raw", sa.Column("org_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_messages_org", "messages_raw", "organisations", ["org_id"], ["id"], ondelete="CASCADE")

    # ── 5. Add org_id to action_items ────────────────────────────────────────
    ai_cols = [c["name"] for c in inspector.get_columns("action_items")]
    if "org_id" not in ai_cols:
        op.add_column("action_items", sa.Column("org_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_actions_org", "action_items", "organisations", ["org_id"], ["id"], ondelete="CASCADE")

    # ── 6. Add org_id to decision_log ────────────────────────────────────────
    if "decision_log" in tables:
        dl_cols = [c["name"] for c in inspector.get_columns("decision_log")]
        if "org_id" not in dl_cols:
            op.add_column("decision_log", sa.Column("org_id", sa.String(36), nullable=True))
            op.create_foreign_key("fk_decisions_org", "decision_log", "organisations", ["org_id"], ["id"], ondelete="CASCADE")

    # ── 7. Migrate source_configs: String PK → Integer PK + org_id ───────────
    sc_cols = [c["name"] for c in inspector.get_columns("source_configs")]
    if "org_id" not in sc_cols:
        # Rename old table, recreate with new schema, migrate data
        op.execute("ALTER TABLE source_configs RENAME TO source_configs_old")
        op.create_table(
            "source_configs",
            sa.Column("id",           sa.Integer(),   primary_key=True, autoincrement=True),
            sa.Column("org_id",       sa.String(36),  nullable=True),
            sa.Column("source",       sa.String(50),  nullable=False),
            sa.Column("config",       JSONB(), nullable=False, server_default="{}"),
            sa.Column("connected_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.UniqueConstraint("org_id", "source", name="uq_org_source"),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], ondelete="CASCADE"),
        )
        op.execute("INSERT INTO source_configs (source, config, connected_at) SELECT source, config, connected_at FROM source_configs_old")
        op.execute("DROP TABLE source_configs_old")

    # ── 8. Add org_id to projects ─────────────────────────────────────────────
    proj_cols = [c["name"] for c in inspector.get_columns("projects")]
    if "org_id" not in proj_cols:
        op.add_column("projects", sa.Column("org_id", sa.String(36), nullable=True))
        op.create_foreign_key("fk_projects_org", "projects", "organisations", ["org_id"], ["id"], ondelete="CASCADE")

    # ── 9. Add org_id to anomaly_events ──────────────────────────────────────
    if "anomaly_events" in tables:
        ae_cols = [c["name"] for c in inspector.get_columns("anomaly_events")]
        if "org_id" not in ae_cols:
            op.add_column("anomaly_events", sa.Column("org_id", sa.String(36), nullable=True))
            op.create_foreign_key("fk_anomaly_org", "anomaly_events", "organisations", ["org_id"], ["id"], ondelete="CASCADE")
        # Remove old user_id column if present
        if "user_id" in ae_cols:
            op.drop_column("anomaly_events", "user_id")


def downgrade() -> None:
    # Remove org_id columns
    for table, fk in [
        ("anomaly_events", "fk_anomaly_org"),
        ("projects",       "fk_projects_org"),
        ("action_items",   "fk_actions_org"),
        ("messages_raw",   "fk_messages_org"),
        ("users",          "fk_users_org"),
    ]:
        try:
            op.drop_constraint(fk, table, type_="foreignkey")
            op.drop_column(table, "org_id")
        except Exception:
            pass

    # Revert roles
    op.execute("UPDATE users SET role = 'owner' WHERE role = 'ceo'")
    op.execute("UPDATE users SET role = 'manager' WHERE role = 'pm'")

    op.drop_table("organisations")
