-- =============================================================================
-- 文档智能系统 · 数据库 DDL v1
-- 目标: PostgreSQL 14+ / Supabase
-- 对齐: docs/contracts/integration-contract-v1.md
-- 执行: psql "$DATABASE_URL" -f sql/schema_v1.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 任务类型（编排层自定义，此处仅示例常见值；应用层可扩展）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 与契约中 task_id 一致的业务标识（对外 API 使用）
    task_id         TEXT NOT NULL UNIQUE,
    task_type       TEXT NOT NULL DEFAULT 'unknown',
    -- queued | running | succeeded | failed | review | cancelled
    status          TEXT NOT NULL DEFAULT 'queued',
    error_code      TEXT,
    error_message   TEXT,
    parent_task_id  UUID REFERENCES tasks (id) ON DELETE SET NULL,
    -- 任意扩展：session_id、用户、优先级等
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    CONSTRAINT tasks_status_check CHECK (
        status IN (
            'queued',
            'running',
            'succeeded',
            'failed',
            'review',
            'cancelled'
        )
    )
);

COMMENT ON TABLE tasks IS '编排任务主表，状态机与契约第 2 节一致';
COMMENT ON COLUMN tasks.task_id IS '业务层 task_id，与抽取 JSON 中 task_id 对齐';
COMMENT ON COLUMN tasks.error_code IS '失败时填写，见契约第 3 节统一错误码';

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks (parent_task_id);

-- ---------------------------------------------------------------------------
-- 任务步骤（可选：parse_doc / extract_fields / save_result / fill_template）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_steps (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid    UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    step_name    TEXT NOT NULL,
    step_order   INT NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'queued',
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code   TEXT,
    error_message TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT task_steps_status_check CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')
    )
);

COMMENT ON TABLE task_steps IS '单任务内多步骤追踪，便于链路审计';

CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps (task_uuid);
CREATE INDEX IF NOT EXISTS idx_task_steps_name ON task_steps (step_name);

-- ---------------------------------------------------------------------------
-- 文档/文件元数据（库内仅存元数据；大文件本体在 Storage/OSS）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_assets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid    UUID REFERENCES tasks (id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'source',
    storage_key  TEXT,
    local_path   TEXT,
    file_name    TEXT,
    file_hash    TEXT,
    mime_type    TEXT,
    byte_size    BIGINT,
    page_count   INT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_assets_role_check CHECK (
        role IN ('source', 'template', 'output', 'aux')
    )
);

COMMENT ON TABLE document_assets IS '文档元数据；storage_key 与 Supabase Storage 等对齐';

CREATE INDEX IF NOT EXISTS idx_document_assets_task ON document_assets (task_uuid);

-- ---------------------------------------------------------------------------
-- B 组抽取结果（JSONB + 版本）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extraction_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid        UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    schema_version   TEXT NOT NULL,
    -- 完整抽取体，结构与契约第 1 节一致（含 fields / source / extras）
    payload          JSONB NOT NULL,
    result_version   INT NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extraction_results_version_unique UNIQUE (task_uuid, result_version)
);

COMMENT ON TABLE extraction_results IS 'B 组输出；payload 为完整 ExtractionResult JSON';
COMMENT ON COLUMN extraction_results.result_version IS '同任务多次抽取递增';

CREATE INDEX IF NOT EXISTS idx_extraction_task ON extraction_results (task_uuid);
CREATE INDEX IF NOT EXISTS idx_extraction_payload_gin ON extraction_results USING gin (payload jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- A 组执行日志
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_execution_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid     UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    action        TEXT NOT NULL,
    summary       TEXT NOT NULL,
    ops_count     INT,
    rollback_id   TEXT,
    detail_ref    TEXT,
    extras        JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE agent_execution_logs IS 'A 组文档编辑/操作日志，契约第 5 节';

CREATE INDEX IF NOT EXISTS idx_agent_exec_task ON agent_execution_logs (task_uuid);
CREATE INDEX IF NOT EXISTS idx_agent_exec_logged_at ON agent_execution_logs (logged_at DESC);

-- ---------------------------------------------------------------------------
-- D 组填表报告
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fill_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid       UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    schema_version  TEXT NOT NULL,
    template_id     TEXT,
    output_file     JSONB NOT NULL,
    filled_fields   JSONB NOT NULL DEFAULT '[]'::jsonb,
    skipped_fields  JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings        JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE fill_reports IS 'D 组填表质检报告，契约第 6 节';
COMMENT ON COLUMN fill_reports.output_file IS '含 storage_key / file_name / mime_type 或 local_path';

CREATE INDEX IF NOT EXISTS idx_fill_reports_task ON fill_reports (task_uuid);

-- ---------------------------------------------------------------------------
-- 审计日志（跨实体）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor         TEXT,
    subject_type  TEXT NOT NULL,
    subject_id    TEXT NOT NULL,
    event         TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE audit_logs IS '通用审计：任务状态变更、人工复核、敏感操作等';

CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_logs (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_logs (subject_type, subject_id);

COMMIT;

-- =============================================================================
-- 可选：更新 updated_at 的触发器（应用层也可自行维护 tasks.updated_at）
-- =============================================================================
-- CREATE OR REPLACE FUNCTION set_updated_at()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   NEW.updated_at = now();
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;
-- CREATE TRIGGER tr_tasks_updated_at
--   BEFORE UPDATE ON tasks
--   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
