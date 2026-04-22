-- ============================================================
--  InsightFlow Executive — Raw Message Storage
--  PFE 2026
-- ============================================================

CREATE TABLE IF NOT EXISTS messages_raw (
    id              VARCHAR(255) PRIMARY KEY,
    source          VARCHAR(50)  NOT NULL,   -- 'gmail' | 'slack' | 'jira'
    author          VARCHAR(255),
    author_email    VARCHAR(255),
    timestamp       TIMESTAMP    NOT NULL,
    title           TEXT,
    content         TEXT,
    item_type       VARCHAR(50),             -- 'email' | 'message' | 'ticket'
    tags            TEXT[],
    thread_id       VARCHAR(255),
    url             TEXT,
    synced_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mr_timestamp ON messages_raw (timestamp);
CREATE INDEX IF NOT EXISTS idx_mr_source    ON messages_raw (source);
CREATE INDEX IF NOT EXISTS idx_mr_thread    ON messages_raw (thread_id);

-- ============================================================
--  Migration v2 — NLP Results
-- ============================================================

ALTER TABLE messages_raw
    ADD COLUMN IF NOT EXISTS sentiment_label    VARCHAR(20),   -- POSITIVE | NEGATIVE | NEUTRAL
    ADD COLUMN IF NOT EXISTS sentiment_score    FLOAT,         -- confidence 0.0–1.0
    ADD COLUMN IF NOT EXISTS emotion_label      VARCHAR(30),   -- anger | frustration | joy | ...
    ADD COLUMN IF NOT EXISTS emotion_score      FLOAT,
    ADD COLUMN IF NOT EXISTS topic              VARCHAR(100),  -- project update | deadline | ...
    ADD COLUMN IF NOT EXISTS business_label     VARCHAR(30),   -- BLOCKED | RISK | URGENT | ...
    ADD COLUMN IF NOT EXISTS business_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS business_reason    TEXT;

CREATE INDEX IF NOT EXISTS idx_mr_sentiment ON messages_raw (sentiment_label);
CREATE INDEX IF NOT EXISTS idx_mr_business  ON messages_raw (business_label);

-- ============================================================
--  Migration v3 — Behavioral Signals
-- ============================================================

ALTER TABLE messages_raw
    ADD COLUMN IF NOT EXISTS hour_sent          SMALLINT,     -- 0-23
    ADD COLUMN IF NOT EXISTS is_weekend         BOOLEAN,      -- Saturday/Sunday
    ADD COLUMN IF NOT EXISTS is_after_hours     BOOLEAN,      -- before 8h or after 20h
    ADD COLUMN IF NOT EXISTS response_delay_min INTEGER,      -- minutes since prev msg in thread
    ADD COLUMN IF NOT EXISTS thread_depth       SMALLINT,     -- number of msgs in thread
    ADD COLUMN IF NOT EXISTS daily_volume       SMALLINT,     -- author's msgs that day
    ADD COLUMN IF NOT EXISTS burnout_score      FLOAT;        -- composite 0.0-1.0

CREATE INDEX IF NOT EXISTS idx_mr_hour    ON messages_raw (hour_sent);
CREATE INDEX IF NOT EXISTS idx_mr_burnout ON messages_raw (burnout_score);

-- ============================================================
--  Migration v4 — Action Items tracker
-- ============================================================

CREATE TABLE IF NOT EXISTS action_items (
    id          SERIAL PRIMARY KEY,
    message_id  VARCHAR(255) REFERENCES messages_raw(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    author      VARCHAR(255),
    source      VARCHAR(50),
    business_label VARCHAR(30),
    note        TEXT,
    done        BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW(),
    done_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_done ON action_items (done);

-- ============================================================
--  Migration v5 — Human Corrections (Continuous Learning)
--  Chaque correction manuelle via l'UI est loggée ici
--  pour constituer le dataset d'entraînement incrémental.
-- ============================================================

CREATE TABLE IF NOT EXISTS human_corrections (
    id              SERIAL PRIMARY KEY,
    message_id      VARCHAR(255) REFERENCES messages_raw(id) ON DELETE CASCADE,
    -- valeurs originales prédites par le modèle
    original_sentiment  VARCHAR(20),
    original_emotion    VARCHAR(30),
    original_business   VARCHAR(30),
    original_topic      VARCHAR(100),
    -- valeurs corrigées par l'humain (NULL = non modifié)
    corrected_sentiment  VARCHAR(20),
    corrected_emotion    VARCHAR(30),
    corrected_business   VARCHAR(30),
    corrected_topic      VARCHAR(100),
    -- texte snapshottée au moment de la correction
    text_snapshot   TEXT,
    -- métadonnées
    corrected_at    TIMESTAMP DEFAULT NOW(),
    used_in_training BOOLEAN DEFAULT FALSE,  -- marqué TRUE après fine-tuning
    training_run_id  VARCHAR(50)             -- identifiant du run de fine-tuning
);

CREATE INDEX IF NOT EXISTS idx_hc_message    ON human_corrections (message_id);
CREATE INDEX IF NOT EXISTS idx_hc_trained    ON human_corrections (used_in_training);
CREATE INDEX IF NOT EXISTS idx_hc_corrected  ON human_corrections (corrected_at);

-- ============================================================
--  Migration v6 — Source-specific metadata (Jira KPIs, etc.)
-- ============================================================

ALTER TABLE messages_raw
    ADD COLUMN IF NOT EXISTS metadata_json JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_mr_metadata ON messages_raw USING gin (metadata_json);

-- ============================================================
--  Migration v7 — Source Configs (credentials per CEO)
-- ============================================================

CREATE TABLE IF NOT EXISTS source_configs (
    source       VARCHAR(50) PRIMARY KEY,
    config       JSONB NOT NULL DEFAULT '{}',
    connected_at TIMESTAMP DEFAULT NOW()
);


-- ============================================================
--  Migration v8 — Decision Log
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_log (
    id          SERIAL PRIMARY KEY,
    title       TEXT        NOT NULL,
    context     TEXT,
    status      VARCHAR(20) DEFAULT 'pending',
    created_at  TIMESTAMP   DEFAULT NOW(),
    decided_at  TIMESTAMP
);
