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
