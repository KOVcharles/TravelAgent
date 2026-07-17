CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trip_history (
    id BIGSERIAL PRIMARY KEY,
    trip_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    origin TEXT,
    destination TEXT,
    start_date TEXT,
    end_date TEXT,
    purpose TEXT,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS request_id TEXT;
ALTER TABLE trip_history ADD COLUMN IF NOT EXISTS request_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_history_request_role
    ON chat_history (user_id, request_id, role)
    WHERE request_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_history_request
    ON trip_history (user_id, request_id)
    WHERE request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_history_user_created
    ON chat_history (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_session_created
    ON chat_history (user_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trip_history_user_created
    ON trip_history (user_id, created_at DESC);
