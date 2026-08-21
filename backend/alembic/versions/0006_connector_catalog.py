"""Add connector_catalog table with default connectors

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

DEFAULTS = [
    ("gmail",           "Gmail",           "📧", "#EA4335", "Communication", "oauth2",   "Emails Google",             True,  False),
    ("outlook",         "Outlook",         "📨", "#0078D4", "Communication", "oauth2",   "Emails Microsoft",          True,  False),
    ("teams",           "Teams",           "💬", "#6264A7", "Communication", "oauth2",   "Messages Microsoft Teams",  True,  False),
    ("slack",           "Slack",           "💼", "#4A154B", "Communication", "bot",      "Canaux Slack",              False, True),
    ("jira",            "Jira",            "🎫", "#0052CC", "Projets",       "api_key",  "Tickets & Sprints",         True,  False),
    ("clickup",         "ClickUp",         "✅", "#7B68EE", "Projets",       "api_key",  "Gestion de tâches",         True,  False),
    ("notion",          "Notion",          "📓", "#333333", "Projets",       "api_key",  "Documentation & Notes",     False, True),
    ("trello",          "Trello",          "📋", "#0052CC", "Projets",       "api_key",  "Boards visuels",            False, True),
    ("google_calendar", "Google Calendar", "📅", "#4285F4", "Agenda",        "oauth2",   "Agenda & Réunions",         False, True),
    ("salesforce",      "Salesforce",      "☁️", "#00A1E0", "CRM",           "oauth2",   "CRM & Ventes",              False, True),
    ("hubspot",         "HubSpot",         "🟠", "#FF7A59", "CRM",           "oauth2",   "Marketing & CRM",           False, True),
    ("github",          "GitHub",          "🐙", "#333333", "Dev",           "oauth2",   "Code & Pull Requests",      False, True),
    ("onedrive",        "OneDrive",        "☁️", "#0078D4", "Stockage",      "oauth2",   "Fichiers Microsoft",        True,  False),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "connector_catalog" not in tables:
        op.create_table(
            "connector_catalog",
            sa.Column("key",         sa.String(50),  primary_key=True),
            sa.Column("name",        sa.String(100), nullable=False),
            sa.Column("icon",        sa.String(10),  server_default="◈"),
            sa.Column("color",       sa.String(7),   server_default="#748cab"),
            sa.Column("category",    sa.String(50),  server_default="Communication"),
            sa.Column("auth_type",   sa.String(30),  server_default="api_key"),
            sa.Column("description", sa.String(255)),
            sa.Column("enabled",     sa.Boolean(),   server_default="true"),
            sa.Column("coming_soon", sa.Boolean(),   server_default="false"),
        )
        for row in DEFAULTS:
            key, name, icon, color, category, auth_type, desc, enabled, coming_soon = row
            op.execute(
                f"INSERT INTO connector_catalog (key,name,icon,color,category,auth_type,description,enabled,coming_soon) "
                f"VALUES ('{key}','{name}','{icon}','{color}','{category}','{auth_type}','{desc}',{str(enabled).lower()},{str(coming_soon).lower()})"
            )


def downgrade() -> None:
    op.drop_table("connector_catalog")
