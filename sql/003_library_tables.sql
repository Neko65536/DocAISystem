-- =============================================================================
-- 文档库模块 · 数据库 DDL
-- 包含：文档空间(document_spaces) 和 文档(library_documents) 两张表
-- 对齐: frontend libraryStore.js / library API
-- 执行: psql "$DATABASE_URL" -f sql/003_library_tables.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 文档空间表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_spaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT,
    name            TEXT NOT NULL,
    icon            TEXT NOT NULL DEFAULT '📁',
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_spaces_user ON document_spaces (user_id);
CREATE INDEX IF NOT EXISTS idx_doc_spaces_created ON document_spaces (created_at DESC);

-- ---------------------------------------------------------------------------
-- 文档表（属于某个空间，文件本体存在 Azure Blob）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id        UUID NOT NULL REFERENCES document_spaces (id) ON DELETE CASCADE,
    user_id         TEXT,
    file_name       TEXT NOT NULL,
    file_size       BIGINT NOT NULL DEFAULT 0,
    mime_type       TEXT,
    file_extension  TEXT,
    storage_key     TEXT,
    blob_url        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_library_docs_space ON library_documents (space_id);
CREATE INDEX IF NOT EXISTS idx_library_docs_user ON library_documents (user_id);
CREATE INDEX IF NOT EXISTS idx_library_docs_created ON library_documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_docs_deleted ON library_documents (deleted_at);

COMMIT;
