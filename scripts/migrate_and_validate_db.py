"""数据库迁移与校验脚本。

用法：
  python scripts/migrate_and_validate_db.py --check-only
  python scripts/migrate_and_validate_db.py --apply --with-seed-check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_config
from db.connection import build_conninfo, db_connection, health_check, is_database_configured

MIGRATION_FILES = [
    ROOT / "sql" / "001_create_sessions_tables.sql",
    ROOT / "sql" / "schema_v1.sql",
    ROOT / "sql" / "002_auth_user_file_scope.sql",
    ROOT / "sql" / "003_library_tables.sql",
]

REQUIRED_TABLES = [
    "users",
    "auth_sessions",
    "sessions",
    "messages",
    "session_files",
    "tasks",
    "task_steps",
    "document_assets",
    "extraction_results",
    "agent_execution_logs",
    "fill_reports",
    "audit_logs",
    "document_spaces",
    "library_documents",
]

REQUIRED_COLUMNS = {
    "sessions": ["user_id"],
    "messages": ["user_id"],
    "session_files": [
        "user_id",
        "source",
        "role",
        "task_uuid",
        "origin_file_id",
        "storage_key",
        "mime_type",
        "file_hash",
        "deleted_at",
    ],
    "tasks": ["user_id", "session_id", "source_mode"],
    "library_documents": ["space_id", "user_id"],
}


def _mask_conninfo(conninfo: str) -> str:
    if "password=" in conninfo:
        parts = conninfo.split(" ")
        masked = []
        for part in parts:
            if part.startswith("password="):
                masked.append("password=***")
            else:
                masked.append(part)
        return " ".join(masked)
    if "://" in conninfo and "@" in conninfo:
        try:
            scheme, rest = conninfo.split("://", 1)
            auth, tail = rest.split("@", 1)
            if ":" in auth:
                user, _ = auth.split(":", 1)
                return f"{scheme}://{user}:***@{tail}"
        except Exception:
            return conninfo
    return conninfo


def _read_sql(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"迁移文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def apply_migrations() -> None:
    cfg = load_config()
    for migration in MIGRATION_FILES:
        sql = _read_sql(migration)
        print(f"[APPLY] {migration.name}")
        with db_connection(cfg) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql)


def validate_schema() -> List[str]:
    cfg = load_config()
    errors: List[str] = []
    with db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            existing_tables = {row[0] for row in cur.fetchall()}

            for table in REQUIRED_TABLES:
                if table not in existing_tables:
                    errors.append(f"缺少表: {table}")

            for table, columns in REQUIRED_COLUMNS.items():
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (table,),
                )
                existing_columns = {row[0] for row in cur.fetchall()}
                for column in columns:
                    if column not in existing_columns:
                        errors.append(f"缺少列: {table}.{column}")

    return errors


def run_seed_check() -> Tuple[bool, str]:
    """在事务中做最小写读校验，最后回滚。"""
    cfg = load_config()
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT seed_check")
                try:
                    cur.execute(
                        """
                        INSERT INTO users (phone, password_hash, display_name)
                        VALUES (%s, %s, %s)
                        RETURNING id::text
                        """,
                        ("13900000000", "pbkdf2_sha256$1$dummy$dummy", "seed-check"),
                    )
                    user_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO sessions (session_id, title, current_mode, user_id)
                        VALUES (%s, %s, %s, %s::uuid)
                        RETURNING id
                        """,
                        ("seed-check-session", "seed-check", "default_conversation", user_id),
                    )
                    session_pk = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO messages (session_id, user_id, role, content, metadata)
                        VALUES (%s, %s::uuid, 'user', 'seed-check', '{}'::jsonb)
                        """,
                        (session_pk, user_id),
                    )

                    cur.execute(
                        """
                        INSERT INTO auth_sessions (user_id, token_hash, expires_at)
                        VALUES (%s::uuid, %s, now() + interval '1 day')
                        """,
                        (user_id, "seed-check-token-hash"),
                    )
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT seed_check")
                    return False, str(exc)
                cur.execute("ROLLBACK TO SAVEPOINT seed_check")
    return True, "seed-check 通过（事务内回滚）"


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移并校验数据库结构")
    parser.add_argument("--apply", action="store_true", help="执行 SQL 迁移")
    parser.add_argument("--check-only", action="store_true", help="仅做结构校验，不执行迁移")
    parser.add_argument("--with-seed-check", action="store_true", help="执行最小写读校验（事务内回滚）")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.database.enabled:
        print("[ERROR] DB_ENABLED 未开启")
        return 2
    if not is_database_configured(cfg):
        print("[ERROR] 数据库连接信息不完整")
        return 2

    conninfo = build_conninfo(cfg)
    print("[INFO] conninfo:", _mask_conninfo(conninfo))

    ok, msg = health_check(cfg)
    if not ok:
        print("[ERROR] 数据库不可用:", msg)
        return 2
    print("[INFO] 数据库连通正常")

    if args.apply and not args.check_only:
        apply_migrations()
        print("[INFO] 迁移执行完成")

    schema_errors = validate_schema()
    if schema_errors:
        print("[ERROR] 结构校验失败:")
        for item in schema_errors:
            print(" -", item)
        return 1
    print("[INFO] 结构校验通过")

    if args.with_seed_check:
        seed_ok, seed_msg = run_seed_check()
        if not seed_ok:
            print("[ERROR] seed-check 失败:", seed_msg)
            return 1
        print("[INFO]", seed_msg)

    print("[DONE] 数据库迁移/校验流程完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
