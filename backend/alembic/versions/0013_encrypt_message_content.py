"""Encrypt messages_raw.title and .content at rest (message/email/ticket body)

messages_raw.title and .content held the actual subject/body of every ingested
message (Gmail, Slack, Jira, Teams, ClickUp, OneDrive...) as plaintext — readable
by anyone with DB access (a leaked backup, an overprivileged DB role). Both are
now Fernet-encrypted via core.models.EncryptedText, keyed by TOKEN_ENCRYPTION_KEY
(must already be set — see core/config.py, same key used by 0011).

Unlike 0011 (OAuth tokens — short-lived, safe to drop and reconnect), this is
the customer's actual business data, so existing rows are re-encrypted in place
here rather than wiped. Batched to avoid loading the whole table into memory.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

BATCH_SIZE = 500


def _fetch_batch(conn, last_id: str):
    return conn.execute(
        sa.text("""
            SELECT id, title, content FROM messages_raw
            WHERE id > :last_id
            ORDER BY id
            LIMIT :batch
        """),
        {"last_id": last_id, "batch": BATCH_SIZE},
    ).fetchall()


def upgrade() -> None:
    from core.crypto import encrypt_str

    conn = op.get_bind()
    last_id = ""
    while True:
        rows = _fetch_batch(conn, last_id)
        if not rows:
            break
        for row in rows:
            conn.execute(
                sa.text("UPDATE messages_raw SET title = :title, content = :content WHERE id = :id"),
                {
                    "title":   encrypt_str(row.title) if row.title is not None else None,
                    "content": encrypt_str(row.content) if row.content is not None else None,
                    "id":      row.id,
                },
            )
        last_id = rows[-1].id


def downgrade() -> None:
    from core.crypto import decrypt_str

    conn = op.get_bind()
    last_id = ""
    while True:
        rows = _fetch_batch(conn, last_id)
        if not rows:
            break
        for row in rows:
            conn.execute(
                sa.text("UPDATE messages_raw SET title = :title, content = :content WHERE id = :id"),
                {
                    "title":   decrypt_str(row.title) if row.title is not None else None,
                    "content": decrypt_str(row.content) if row.content is not None else None,
                    "id":      row.id,
                },
            )
        last_id = rows[-1].id
