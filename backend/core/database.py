"""
PostgreSQL connection — SQLAlchemy engine + session factory.
DATABASE_URL can be overridden via .env or environment variable.
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from core.config import settings
from core.models import Base

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
    Create tables via Alembic migrations (alembic upgrade head).
    Falls back to schema.sql if Alembic is not configured yet.
    Returns True on success, False if PostgreSQL is unreachable.
    """
    import os, subprocess, sys
    alembic_ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
    if os.path.exists(alembic_ini):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info("[DB] Alembic migrations applied.")
                return True
            else:
                logger.warning("[DB] Alembic error: %s", result.stderr)
        except Exception as e:
            logger.warning("[DB] Alembic failed: %s", e)

    # Fallback — schema.sql brut
    schema_path = os.path.join(os.path.dirname(__file__), "..", "data", "etl", "schema.sql")
    try:
        with open(schema_path) as f:
            sql = f.read()
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        logger.info("[DB] Schema initialized via schema.sql (fallback).")
        return True
    except Exception as e:
        logger.warning("[DB] Could not initialize schema: %s", e)
        return False
