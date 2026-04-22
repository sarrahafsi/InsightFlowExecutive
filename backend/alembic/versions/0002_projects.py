"""Add projects tables — projects, project_members, project_sources, project_notes, project_files, project_activities

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("color",       sa.String(7),   server_default="#3e5c76"),
        sa.Column("created_by",  sa.String(255)),
        sa.Column("created_at",  sa.TIMESTAMP,   server_default=sa.func.now()),
        sa.Column("updated_at",  sa.TIMESTAMP,   server_default=sa.func.now()),
    )

    op.create_table(
        "project_members",
        sa.Column("id",         sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",       sa.String(255)),
        sa.Column("email",      sa.String(255)),
        sa.Column("role",       sa.String(50),  server_default="member"),
        sa.Column("added_at",   sa.TIMESTAMP,   server_default=sa.func.now()),
    )

    op.create_table(
        "project_sources",
        sa.Column("id",           sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("project_id",   sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type",  sa.String(50)),
        sa.Column("config",       postgresql.JSONB, server_default="{}"),
        sa.Column("connected_at", sa.TIMESTAMP,  server_default=sa.func.now()),
    )

    op.create_table(
        "project_notes",
        sa.Column("id",         sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",      sa.String(255)),
        sa.Column("content",    sa.Text),
        sa.Column("created_by", sa.String(255)),
        sa.Column("created_at", sa.TIMESTAMP,  server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP,  server_default=sa.func.now()),
    )

    op.create_table(
        "project_files",
        sa.Column("id",          sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("project_id",  sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename",    sa.String(255), nullable=False),
        sa.Column("file_path",   sa.Text),
        sa.Column("source",      sa.String(50)),
        sa.Column("size_bytes",  sa.BigInteger),
        sa.Column("mime_type",   sa.String(100)),
        sa.Column("uploaded_by", sa.String(255)),
        sa.Column("uploaded_at", sa.TIMESTAMP,  server_default=sa.func.now()),
    )

    op.create_table(
        "project_activities",
        sa.Column("id",         sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor",      sa.String(255)),
        sa.Column("action",     sa.String(100)),
        sa.Column("detail",     sa.Text),
        sa.Column("created_at", sa.TIMESTAMP,  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("project_activities")
    op.drop_table("project_files")
    op.drop_table("project_notes")
    op.drop_table("project_sources")
    op.drop_table("project_members")
    op.drop_table("projects")
