-- =============================================================================
-- 文档智能系统 · 认证 / 用户归属 / 统一文件元数据迁移
-- 目标: PostgreSQL 14+ / Supabase
-- 说明:
--   1. 先执行现有 schema，再执行本文件
--   2. 本文件保持幂等，便于重复执行
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'disabled', 'locked'))
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users (phone);
CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users (updated_at DESC);

-- ---------------------------------------------------------------------------
-- 登录会话表（访问令牌黑名单 / 退出登录 / 多端登录追踪）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    user_agent      TEXT,
    ip_address      TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at ON auth_sessions (revoked_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_last_used_at ON auth_sessions (last_used_at DESC);

-- ---------------------------------------------------------------------------
-- 给现有会话 / 消息 / 文件表补用户归属
-- ---------------------------------------------------------------------------
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload';

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'source';

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS task_uuid UUID;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS origin_file_id INTEGER;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS storage_key TEXT;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS mime_type TEXT;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS file_hash TEXT;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE session_files
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS session_id VARCHAR(64);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS source_mode TEXT;

ALTER TABLE document_assets
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE document_assets
    ADD COLUMN IF NOT EXISTS session_id VARCHAR(64);

-- ---------------------------------------------------------------------------
-- 约束补强（重复执行时自动跳过）
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'sessions_user_id_fkey'
    ) THEN
        ALTER TABLE sessions
            ADD CONSTRAINT sessions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'session_files_file_type_check'
    ) THEN
        ALTER TABLE session_files
            DROP CONSTRAINT session_files_file_type_check;
    END IF;

    ALTER TABLE session_files
        ADD CONSTRAINT session_files_file_type_check
        CHECK (file_type IN ('data', 'template', 'generated'));
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'messages_user_id_fkey'
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT messages_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'session_files_user_id_fkey'
    ) THEN
        ALTER TABLE session_files
            ADD CONSTRAINT session_files_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'session_files_task_uuid_fkey'
    ) THEN
        ALTER TABLE session_files
            ADD CONSTRAINT session_files_task_uuid_fkey
            FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'tasks_user_id_fkey'
    ) THEN
        ALTER TABLE tasks
            ADD CONSTRAINT tasks_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'document_assets_user_id_fkey'
    ) THEN
        ALTER TABLE document_assets
            ADD CONSTRAINT document_assets_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'document_assets_task_uuid_fkey'
    ) THEN
        ALTER TABLE document_assets
            ADD CONSTRAINT document_assets_task_uuid_fkey
            FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE SET NULL;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 高频查询索引
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_updated_at ON sessions (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_created_at ON messages (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_session_files_user_id ON session_files (user_id);
CREATE INDEX IF NOT EXISTS idx_session_files_session_created_at ON session_files (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_files_task_uuid ON session_files (task_uuid);
CREATE INDEX IF NOT EXISTS idx_session_files_deleted_at ON session_files (deleted_at);
CREATE INDEX IF NOT EXISTS idx_session_files_source ON session_files (source);

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks (session_id);

CREATE INDEX IF NOT EXISTS idx_document_assets_user_id ON document_assets (user_id);
CREATE INDEX IF NOT EXISTS idx_document_assets_session_id ON document_assets (session_id);

COMMIT;
