"""
SQLAlchemy ORM models — InsightFlow Executive (multi-tenant)
Tables : organisations · users
         messages_raw · action_items · human_corrections · source_configs
         connector_catalog
         projects · project_members · project_sources · project_notes · project_files · project_activities
         decision_log · anomaly_events
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, Column, Float, ForeignKey,
    Integer, SmallInteger, String, Text, TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Organisation (tenant = client) ────────────────────────────────────────────

class Organisation(Base):
    __tablename__ = "organisations"

    id         = Column(String(36),  primary_key=True, default=lambda: str(uuid4()))
    name       = Column(String(255), nullable=False)
    plan       = Column(String(50),  default="free")   # free | pro | enterprise
    created_at = Column(TIMESTAMP,   default=datetime.utcnow)

    users       = relationship("User",         back_populates="organisation", passive_deletes=True)
    projects    = relationship("Project",      back_populates="organisation", passive_deletes=True)
    source_cfgs = relationship("SourceConfig", back_populates="organisation", passive_deletes=True)


class MessageRaw(Base):
    __tablename__ = "messages_raw"

    id                  = Column(String(255),  primary_key=True)
    org_id              = Column(String(36),   ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    source              = Column(String(50),   nullable=False)
    author              = Column(String(255))
    author_email        = Column(String(255))
    timestamp           = Column(TIMESTAMP,    nullable=False)
    title               = Column(Text)
    content             = Column(Text)
    item_type           = Column(String(50))
    tags                = Column(ARRAY(Text))
    thread_id           = Column(String(255))
    url                 = Column(Text)
    synced_at           = Column(TIMESTAMP,    default=datetime.utcnow)

    # NLP
    sentiment_label     = Column(String(20))
    sentiment_score     = Column(Float)
    emotion_label       = Column(String(30))
    emotion_score       = Column(Float)
    topic               = Column(String(100))
    business_label      = Column(String(30))
    business_confidence = Column(Float)
    business_reason     = Column(Text)

    # Behavioral
    hour_sent           = Column(SmallInteger)
    is_weekend          = Column(Boolean)
    is_after_hours      = Column(Boolean)
    response_delay_min  = Column(Integer)
    thread_depth        = Column(SmallInteger)
    daily_volume        = Column(SmallInteger)
    burnout_score       = Column(Float)

    # Source-specific metadata
    metadata_json       = Column(JSONB, default=dict)

    # Relations
    action_items        = relationship("ActionItem",       back_populates="message", passive_deletes=True)
    corrections         = relationship("HumanCorrection",  back_populates="message", passive_deletes=True)


class ActionItem(Base):
    __tablename__ = "action_items"

    id              = Column(Integer,      primary_key=True, autoincrement=True)
    org_id          = Column(String(36),   ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    message_id      = Column(String(255),  ForeignKey("messages_raw.id", ondelete="SET NULL"), nullable=True)
    title           = Column(Text,         nullable=False)
    author          = Column(String(255))
    source          = Column(String(50))
    business_label  = Column(String(30))
    note            = Column(Text)
    done            = Column(Boolean,      default=False)
    created_at      = Column(TIMESTAMP,    default=datetime.utcnow)
    done_at         = Column(TIMESTAMP,    nullable=True)

    message         = relationship("MessageRaw", back_populates="action_items")


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    org_id      = Column(String(36),  ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    title       = Column(Text,        nullable=False)
    context     = Column(Text)
    status      = Column(String(20),  default="pending")   # pending | decided | cancelled
    created_at  = Column(TIMESTAMP,   default=datetime.utcnow)
    decided_at  = Column(TIMESTAMP,   nullable=True)


class HumanCorrection(Base):
    __tablename__ = "human_corrections"

    id                  = Column(Integer,     primary_key=True, autoincrement=True)
    message_id          = Column(String(255), ForeignKey("messages_raw.id", ondelete="CASCADE"))

    original_sentiment  = Column(String(20))
    original_emotion    = Column(String(30))
    original_business   = Column(String(30))
    original_topic      = Column(String(100))

    corrected_sentiment = Column(String(20))
    corrected_emotion   = Column(String(30))
    corrected_business  = Column(String(30))
    corrected_topic     = Column(String(100))

    text_snapshot       = Column(Text)
    corrected_at        = Column(TIMESTAMP,   default=datetime.utcnow)
    used_in_training    = Column(Boolean,     default=False)
    training_run_id     = Column(String(50))

    message             = relationship("MessageRaw", back_populates="corrections")


class SourceConfig(Base):
    __tablename__ = "source_configs"
    __table_args__ = (UniqueConstraint("org_id", "source", name="uq_org_source"),)

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    org_id       = Column(String(36),  ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    source       = Column(String(50),  nullable=False)
    config       = Column(JSONB,       nullable=False, default=dict)
    connected_at = Column(TIMESTAMP,   default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="source_cfgs")


# ── Connector Catalog (platform-level, managed by superadmin) ─────────────────

class ConnectorCatalog(Base):
    __tablename__ = "connector_catalog"

    key         = Column(String(50),  primary_key=True)   # gmail | jira | slack ...
    name        = Column(String(100), nullable=False)
    icon        = Column(String(10),  default="◈")
    color       = Column(String(7),   default="#748cab")
    category    = Column(String(50),  default="Communication")
    auth_type   = Column(String(30),  default="api_key")
    description = Column(String(255))
    enabled     = Column(Boolean,     default=True)
    coming_soon = Column(Boolean,     default=False)


# ── Projects ──────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id          = Column(String(36),  primary_key=True, default=lambda: str(uuid4()))
    org_id      = Column(String(36),  ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    name        = Column(String(255), nullable=False)
    description = Column(Text)
    color       = Column(String(7),   default="#3e5c76")
    created_by  = Column(String(255))
    status      = Column(String(20),   default="on_track")   # on_track | at_risk | off_track
    progress    = Column(SmallInteger, default=0)            # 0–100
    blockers    = Column(SmallInteger, default=0)
    risk_level  = Column(String(20),   default="Low")        # Low | Medium | High
    sentiment   = Column(String(20),   default="Neutral")    # Positive | Neutral | Negative
    created_at  = Column(TIMESTAMP,    default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP,   default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="projects")
    members      = relationship("ProjectMember",   back_populates="project", cascade="all, delete-orphan")
    sources      = relationship("ProjectSource",   back_populates="project", cascade="all, delete-orphan")
    notes        = relationship("ProjectNote",     back_populates="project", cascade="all, delete-orphan")
    files        = relationship("ProjectFile",     back_populates="project", cascade="all, delete-orphan")
    activities   = relationship("ProjectActivity", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    project_id = Column(String(36),  ForeignKey("projects.id", ondelete="CASCADE"))
    name       = Column(String(255))
    email      = Column(String(255))
    role       = Column(String(50),  default="member")   # owner | member | viewer
    added_at   = Column(TIMESTAMP,   default=datetime.utcnow)

    project    = relationship("Project", back_populates="members")


class ProjectSource(Base):
    __tablename__ = "project_sources"

    id           = Column(Integer,    primary_key=True, autoincrement=True)
    project_id   = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"))
    source_type  = Column(String(50)) # onedrive | teams
    config       = Column(JSONB,      default=dict)   # folder_id, channel_id …
    connected_at = Column(TIMESTAMP,  default=datetime.utcnow)

    project      = relationship("Project", back_populates="sources")


class ProjectNote(Base):
    __tablename__ = "project_notes"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    project_id = Column(String(36),  ForeignKey("projects.id", ondelete="CASCADE"))
    title      = Column(String(255))
    content    = Column(Text)
    created_by = Column(String(255))
    created_at = Column(TIMESTAMP,   default=datetime.utcnow)
    updated_at = Column(TIMESTAMP,   default=datetime.utcnow)

    project    = relationship("Project", back_populates="notes")


class ProjectFile(Base):
    __tablename__ = "project_files"

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    project_id  = Column(String(36),  ForeignKey("projects.id", ondelete="CASCADE"))
    filename    = Column(String(255), nullable=False)
    file_path   = Column(Text)
    source      = Column(String(50))  # upload | onedrive
    size_bytes  = Column(BigInteger)
    mime_type   = Column(String(100))
    uploaded_by = Column(String(255))
    uploaded_at = Column(TIMESTAMP,   default=datetime.utcnow)

    project     = relationship("Project", back_populates="files")


class ProjectActivity(Base):
    __tablename__ = "project_activities"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    project_id = Column(String(36),  ForeignKey("projects.id", ondelete="CASCADE"))
    actor      = Column(String(255))
    action     = Column(String(100)) # created_note | uploaded_file | linked_source | created_project
    detail     = Column(Text)
    created_at = Column(TIMESTAMP,   default=datetime.utcnow)

    project    = relationship("Project", back_populates="activities")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    org_id          = Column(String(36),  ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    email           = Column(String(255), nullable=False, unique=True)
    full_name       = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(20),  default="pm")   # superadmin | ceo | pm
    is_active       = Column(Boolean,     default=True)
    created_at      = Column(TIMESTAMP,   default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="users")


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    org_id          = Column(String(36),  ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    source          = Column(String(50),  nullable=False)   # gmail | jira | slack | all
    metric          = Column(String(100), nullable=False)   # nb_messages | nb_blocked | nb_night_msgs ...
    current_value   = Column(Float,       nullable=False)
    baseline_value  = Column(Float,       nullable=False)
    anomaly_score   = Column(Float,       nullable=False)   # Isolation Forest score (négatif = plus anormal)
    severity        = Column(String(20),  nullable=False)   # low | medium | high
    description     = Column(Text)
    detected_at     = Column(TIMESTAMP,   default=datetime.utcnow)
    window_days     = Column(Integer,     default=7)        # fenêtre d'observation utilisée
    is_read         = Column(Boolean,     default=False)
