"""七牛云存储连通性测试脚本。"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    from qiniu import Auth, BucketManager, put_file_v2
except Exception as exc:  # pragma: no cover
    raise RuntimeError("未安装 qiniu 依赖，请先安装 requirements.txt") from exc


def _load_env() -> None:
    """加载项目根目录 .env。"""
    if load_dotenv is None:
        return
    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(root_env)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少环境变量: {name}")
    return value


def main() -> int:
    _load_env()

    provider = os.getenv("STORAGE_PROVIDER", "").strip().lower()
    if provider != "qiniu":
        print(f"[WARN] 当前 STORAGE_PROVIDER={provider}，不是 qiniu，仍继续做七牛连通性测试")

    ak = _required_env("QINIU_AK")
    sk = _required_env("QINIU_SK")
    bucket_name = _required_env("QINIU_BUCKET_NAME")
    region_id = os.getenv("QINIU_REGION_ID", "cn-east-1").strip()

    print("=== 七牛云配置检查 ===")
    print(f"bucket: {bucket_name}")
    print(f"region: {region_id}")

    q = Auth(ak, sk)
    bucket = BucketManager(q)

    # 1) 先做 list 能力检查
    ret, eof, info = bucket.list(bucket_name, limit=1)
    if info.status_code != 200:
        print("[FAIL] Bucket list 失败")
        print(f"status: {info.status_code}")
        print(f"error: {info.error}")
        return 1
    print("[OK] Bucket list 成功")

    # 2) 上传一个临时文件
    test_name = f"connectivity_test_{uuid.uuid4().hex[:8]}.txt"
    local_path = Path(__file__).resolve().parent / test_name
    local_path.write_text(
        "七牛云连通性测试\n"
        f"time: {datetime.now().isoformat()}\n"
        f"bucket: {bucket_name}\n",
        encoding="utf-8",
    )

    try:
        token = q.upload_token(bucket_name, test_name, 3600)
        ret, info = put_file_v2(token, test_name, str(local_path))
        if info.status_code != 200:
            print("[FAIL] 上传失败")
            print(f"status: {info.status_code}")
            print(f"error: {info.error}")
            return 1

        print("[OK] 上传成功")
        print(f"key: {ret.get('key', test_name)}")

        # 3) 删除临时文件，验证写后删能力
        _, del_info = bucket.delete(bucket_name, test_name)
        if del_info.status_code != 200:
            print("[WARN] 上传成功但删除失败")
            print(f"status: {del_info.status_code}")
            print(f"error: {del_info.error}")
            return 2

        print("[OK] 删除成功")
        print("[DONE] 七牛云连通性测试通过")
        return 0
    finally:
        if local_path.exists():
            local_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
