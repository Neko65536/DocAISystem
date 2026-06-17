"""Azure PostgreSQL 连接测试脚本。"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保可以导入 src 下模块
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_config
from db.connection import build_conninfo, health_check


def _mask_conninfo(conninfo: str) -> str:
    """避免在输出中泄露密码。"""
    if "password=" in conninfo:
        # libpq keyword 风格: ... password=xxx ...
        parts = conninfo.split(" ")
        masked = []
        for p in parts:
            if p.startswith("password="):
                masked.append("password=***")
            else:
                masked.append(p)
        return " ".join(masked)

    if "://" in conninfo and "@" in conninfo:
        # URL 风格: postgresql://user:pass@host/db
        try:
            scheme, rest = conninfo.split("://", 1)
            auth, tail = rest.split("@", 1)
            if ":" in auth:
                user, _ = auth.split(":", 1)
                return f"{scheme}://{user}:***@{tail}"
        except Exception:
            return conninfo

    return conninfo


def main() -> int:
    cfg = load_config()
    db_cfg = cfg.database

    print("=== PostgreSQL 配置检查 ===")
    print(f"enabled: {db_cfg.enabled}")
    print(f"host: {db_cfg.host}")
    print(f"port: {db_cfg.port}")
    print(f"database: {db_cfg.database}")
    print(f"user: {db_cfg.username}")
    print(f"sslmode: {db_cfg.sslmode}")

    try:
        conninfo = build_conninfo(cfg)
        print("conninfo:", _mask_conninfo(conninfo))
    except Exception as e:
        print("构建连接串失败:", str(e))
        return 2

    ok, msg = health_check(cfg)
    print("=== 连接测试结果 ===")
    print("success:", ok)
    print("message:", msg)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
