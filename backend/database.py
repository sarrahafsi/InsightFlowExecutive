"""
PostgreSQL connection — SQLAlchemy engine + session factory.
DATABASE_URL can be overridden via .env or environment variable.
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # reconnect if the connection was dropped
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> bool:
    """
    Create tables and views from schema.sql.
    Returns True on success, False if PostgreSQL is unreachable.
    """
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "etl", "schema.sql")
    try:
        with open(schema_path) as f:
            sql = f.read()
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        logger.info("[DB] Schema initialized.")
        return True
    except Exception as e:
        logger.warning("[DB] Could not initialize schema: %s", e)
        return False
