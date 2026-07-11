ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

CREATE TABLE IF NOT EXISTS active_trip_contexts (
    user_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    context_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS skill_settings (
    skill_name TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    config_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skill_execution_runs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    parent_run_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_skill_runs_started_at
    ON skill_execution_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_skill_runs_skill_started
    ON skill_execution_runs (skill_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_skill_runs_request
    ON skill_execution_runs (request_id);
