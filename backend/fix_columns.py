from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS blockers SMALLINT DEFAULT 0"))
    conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'Low'"))
    conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS sentiment VARCHAR(20) DEFAULT 'Neutral'"))
    conn.commit()

print("Colonnes ajoutées avec succès !")
