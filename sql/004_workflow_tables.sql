BEGIN;

CREATE TABLE IF NOT EXISTS user_workflows (
    workflow_id VARCHAR(64) PRIMARY KEY,
    user_id     UUID,
    name        VARCHAR(255) NOT NULL DEFAULT '未命名',
    icon        VARCHAR(32) NOT NULL DEFAULT '🔧',
    type        VARCHAR(16) NOT NULL DEFAULT 'custom',
    nodes       JSONB NOT NULL DEFAULT '[]'::jsonb,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_workflows
    ADD COLUMN IF NOT EXISTS user_id UUID;

CREATE INDEX IF NOT EXISTS idx_user_workflows_updated
    ON user_workflows(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_workflows_type
    ON user_workflows(type);
CREATE INDEX IF NOT EXISTS idx_user_workflows_user
    ON user_workflows(user_id);

CREATE TABLE IF NOT EXISTS workflow_executions (
    execution_id       VARCHAR(64) PRIMARY KEY,
    user_id            UUID,
    status             VARCHAR(32) NOT NULL DEFAULT 'running',
    error_code         VARCHAR(64),
    progress           INT NOT NULL DEFAULT 0,
    current_file_index INT NOT NULL DEFAULT 0,
    total_files        INT NOT NULL DEFAULT 0,
    current_file_name  TEXT NOT NULL DEFAULT '',
    logs               JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_files       JSONB NOT NULL DEFAULT '[]'::jsonb,
    error              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workflow_executions
    ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE workflow_executions
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_workflow_exec_updated
    ON workflow_executions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_exec_status
    ON workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_exec_user
    ON workflow_executions(user_id);

COMMIT;
