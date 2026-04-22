"""Initial schema — messages_raw, action_items, human_corrections, source_configs

Revision ID: 0001
Revises:
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── messages_raw ──────────────────────────────────────────
    op.create_table(
        "messages_raw",
        sa.Column("id",                  sa.String(255),       primary_key=True),
        sa.Column("source",              sa.String(50),        nullable=False),
        sa.Column("author",              sa.String(255)),
        sa.Column("author_email",        sa.String(255)),
        sa.Column("timestamp",           sa.TIMESTAMP(),       nullable=False),
        sa.Column("title",               sa.Text()),
        sa.Column("content",             sa.Text()),
        sa.Column("item_type",           sa.String(50)),
        sa.Column("tags",                postgresql.ARRAY(sa.Text())),
        sa.Column("thread_id",           sa.String(255)),
        sa.Column("url",                 sa.Text()),
        sa.Column("synced_at",           sa.TIMESTAMP(),       server_default=sa.text("NOW()")),
        # NLP
        sa.Column("sentiment_label",     sa.String(20)),
        sa.Column("sentiment_score",     sa.Float()),
        sa.Column("emotion_label",       sa.String(30)),
        sa.Column("emotion_score",       sa.Float()),
        sa.Column("topic",               sa.String(100)),
        sa.Column("business_label",      sa.String(30)),
        sa.Column("business_confidence", sa.Float()),
        sa.Column("business_reason",     sa.Text()),
        # Behavioral
        sa.Column("hour_sent",           sa.SmallInteger()),
        sa.Column("is_weekend",          sa.Boolean()),
        sa.Column("is_after_hours",      sa.Boolean()),
        sa.Column("response_delay_min",  sa.Integer()),
        sa.Column("thread_depth",        sa.SmallInteger()),
        sa.Column("daily_volume",        sa.SmallInteger()),
        sa.Column("burnout_score",       sa.Float()),
        # Metadata
        sa.Column("metadata_json",       postgresql.JSONB(),   server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_mr_timestamp", "messages_raw", ["timestamp"])
    op.create_index("idx_mr_source",    "messages_raw", ["source"])
    op.create_index("idx_mr_thread",    "messages_raw", ["thread_id"])
    op.create_index("idx_mr_sentiment", "messages_raw", ["sentiment_label"])
    op.create_index("idx_mr_business",  "messages_raw", ["business_label"])
    op.create_index("idx_mr_hour",      "messages_raw", ["hour_sent"])
    op.create_index("idx_mr_burnout",   "messages_raw", ["burnout_score"])
    op.create_index(
        "idx_mr_metadata", "messages_raw", ["metadata_json"],
        postgresql_using="gin",
    )

    # ── action_items ──────────────────────────────────────────
    op.create_table(
        "action_items",
        sa.Column("id",             sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("message_id",     sa.String(255),   sa.ForeignKey("messages_raw.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title",          sa.Text(),        nullable=False),
        sa.Column("author",         sa.String(255)),
        sa.Column("source",         sa.String(50)),
        sa.Column("business_label", sa.String(30)),
        sa.Column("note",           sa.Text()),
        sa.Column("done",           sa.Boolean(),     server_default=sa.text("FALSE")),
        sa.Column("created_at",     sa.TIMESTAMP(),   server_default=sa.text("NOW()")),
        sa.Column("done_at",        sa.TIMESTAMP()),
    )
    op.create_index("idx_ai_done", "action_items", ["done"])

    # ── human_corrections ─────────────────────────────────────
    op.create_table(
        "human_corrections",
        sa.Column("id",                  sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("message_id",          sa.String(255),  sa.ForeignKey("messages_raw.id", ondelete="CASCADE")),
        sa.Column("original_sentiment",  sa.String(20)),
        sa.Column("original_emotion",    sa.String(30)),
        sa.Column("original_business",   sa.String(30)),
        sa.Column("original_topic",      sa.String(100)),
        sa.Column("corrected_sentiment", sa.String(20)),
        sa.Column("corrected_emotion",   sa.String(30)),
        sa.Column("corrected_business",  sa.String(30)),
        sa.Column("corrected_topic",     sa.String(100)),
        sa.Column("text_snapshot",       sa.Text()),
        sa.Column("corrected_at",        sa.TIMESTAMP(),  server_default=sa.text("NOW()")),
        sa.Column("used_in_training",    sa.Boolean(),    server_default=sa.text("FALSE")),
        sa.Column("training_run_id",     sa.String(50)),
    )
    op.create_index("idx_hc_message",   "human_corrections", ["message_id"])
    op.create_index("idx_hc_trained",   "human_corrections", ["used_in_training"])
    op.create_index("idx_hc_corrected", "human_corrections", ["corrected_at"])

    # ── source_configs ────────────────────────────────────────
    op.create_table(
        "source_configs",
        sa.Column("source",       sa.String(50),    primary_key=True),
        sa.Column("config",       postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("connected_at", sa.TIMESTAMP(),   server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("source_configs")
    op.drop_table("human_corrections")
    op.drop_table("action_items")
    op.drop_table("messages_raw")
