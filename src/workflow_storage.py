"""
工作流持久化存储模块
优先使用 PostgreSQL 数据库；数据库未启用时降级到 JSON 文件。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SystemConfig, get_config
from db.workflow_repository import (
    db_delete_workflow,
    db_get_workflow,
    db_list_workflows,
    db_save_workflow,
    is_db_enabled,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# JSON 文件降级存储路径
_WORKFLOWS_FILE = "user_workflows.json"


def _get_storage_path(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    storage_dir = Path(cfg.work_dir) / "workflows"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir / _WORKFLOWS_FILE


def _load_all(config: Optional[SystemConfig] = None) -> Dict[str, Any]:
    path = _get_storage_path(config)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"加载工作流失败: {e}")
        return {}


def _save_all(data: Dict[str, Any], config: Optional[SystemConfig] = None) -> None:
    path = _get_storage_path(config)
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
    except IOError as e:
        logger.error(f"保存工作流失败: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def list_workflows(
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    获取所有用户自定义工作流列表（不含完整 nodes）。
    优先数据库；未启用时降级 JSON。
    """
    if is_db_enabled(config):
        return db_list_workflows(config, user_id=user_id)

    # JSON 降级
    all_data = _load_all(config)
    results = [
        {
            "id": wf_id,
            "name": wf.get("name", "未命名"),
            "icon": wf.get("icon", "🔧"),
            "type": wf.get("type", "custom"),
            "created_at": wf.get("created_at", ""),
            "updated_at": wf.get("updated_at", ""),
        }
        for wf_id, wf in all_data.items()
        if not user_id or str(wf.get("user_id") or "") == str(user_id)
    ]
    results.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return results


def get_workflow(
    workflow_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    获取指定工作流的完整配置（含 nodes、config）。
    """
    if is_db_enabled(config):
        return db_get_workflow(workflow_id, config, user_id=user_id)

    # JSON 降级
    all_data = _load_all(config)
    wf = all_data.get(workflow_id)
    if not wf or (user_id and str(wf.get("user_id") or "") != str(user_id)):
        return None
    return {
        "id": workflow_id,
        "name": wf.get("name", "未命名"),
        "icon": wf.get("icon", "🔧"),
        "type": wf.get("type", "custom"),
        "created_at": wf.get("created_at", ""),
        "updated_at": wf.get("updated_at", ""),
        "nodes": wf.get("nodes", []),
        "edges": wf.get("edges", wf.get("config", {}).get("edges", [])),
        "config": wf.get("config", {}),
    }


def save_workflow(
    workflow_id: str,
    name: str,
    icon: str = "🔧",
    nodes: Optional[List[Dict[str, Any]]] = None,
    config_data: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    保存（新建或更新）一个用户工作流。
    优先数据库；未启用时降级 JSON 文件。
    """
    if is_db_enabled(config):
        db_config = dict(config_data or {})
        db_config["edges"] = edges or db_config.get("edges", [])
        wf = db_save_workflow(
            workflow_id, name, icon, nodes, db_config, config, user_id=user_id
        )
        wf["edges"] = db_config.get("edges", [])
        return wf

    # JSON 降级
    from datetime import datetime, timezone

    all_data = _load_all(config)
    now = datetime.now(timezone.utc).isoformat()
    existing = all_data.get(workflow_id)
    if (
        existing
        and user_id
        and existing.get("user_id")
        and str(existing.get("user_id")) != str(user_id)
    ):
        raise PermissionError("工作流不属于当前用户")
    created_at = existing.get("created_at", now) if existing else now

    all_data[workflow_id] = {
        "id": workflow_id,
        "user_id": user_id,
        "name": name,
        "icon": icon,
        "type": "custom",
        "created_at": created_at,
        "updated_at": now,
        "nodes": nodes or [],
        "edges": edges or (config_data or {}).get("edges", []),
        "config": config_data or {},
    }
    _save_all(all_data, config)
    logger.info(f"工作流已保存: {workflow_id} ({name})")
    return {
        "id": workflow_id,
        "name": name,
        "icon": icon,
        "type": "custom",
        "created_at": created_at,
        "updated_at": now,
        "nodes": nodes or [],
        "edges": edges or (config_data or {}).get("edges", []),
        "config": config_data or {},
    }


def delete_workflow(
    workflow_id: str,
    config: Optional[SystemConfig] = None,
    user_id: Optional[str] = None,
) -> bool:
    """
    删除指定工作流。
    """
    if is_db_enabled(config):
        deleted = db_delete_workflow(workflow_id, config, user_id=user_id)
        if deleted:
            return True
        # 兼容历史/降级存储：数据库启用后，旧工作流可能仍存在 JSON 文件中。
        logger.warning(f"数据库中未删除工作流，尝试删除 JSON 降级存储: {workflow_id}")

    # JSON 降级
    all_data = _load_all(config)
    wf = all_data.get(workflow_id)
    if not wf or (user_id and str(wf.get("user_id") or "") != str(user_id)):
        return False
    if wf.get("type") == "template":
        logger.warning(f"禁止删除模板工作流: {workflow_id}")
        return False
    del all_data[workflow_id]
    _save_all(all_data, config)
    logger.info(f"工作流已删除: {workflow_id}")
    return True
