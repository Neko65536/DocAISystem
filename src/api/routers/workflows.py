"""
Workflow API 路由
支持前端工作流节点的执行调度，逐文件处理。

端点：
  POST /api/workflows/execute        启动执行，返回 execution_id
  GET  /api/workflows/executions/{id}  查询执行状态
  GET  /api/workflows/templates       获取工作流模板列表
  GET  /api/workflows/templates/{id}  获取指定模板
  GET  /api/workflows                获取用户工作流列表
  POST /api/workflows                保存工作流（新建或更新）
  DELETE /api/workflows/{id}         删除工作流
  GET  /api/workflows/{id}           获取单个工作流完整配置
  GET  /api/workflows/models         获取可用 LLM 模型
  GET  /api/workflows/languages      获取支持的目标语言
  GET  /api/workflows/output-formats  获取支持的输出格式
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import SystemConfig, get_config
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType
from core.storage import build_blob_name, upload_file_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.connection import is_database_configured
from db.workflow_repository import db_load_execution_states, db_save_execution_states, is_db_enabled
from db.session_repository import add_session_file, get_session_by_id
from utils.logger import get_logger
from workflow_storage import delete_workflow, get_workflow, list_workflows, save_workflow

router = APIRouter(prefix="/api/workflows", tags=["工作流编排"])
logger = get_logger(__name__)

# ==================== 执行状态存储（进程内内存） ====================
# key: execution_id, value: state dict
_EXECUTION_STATES: Dict[str, dict] = {}


def _execution_states_file(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    state_dir = Path(cfg.work_dir) / "workflows"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "execution_states.json"


def _load_execution_states(config: Optional[SystemConfig] = None) -> Dict[str, dict]:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        loaded = db_load_execution_states(cfg)
        if loaded:
            return loaded

    path = _execution_states_file(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning(f"加载工作流执行状态失败: {exc}")
    return {}


def _persist_execution_states(config: Optional[SystemConfig] = None) -> None:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        if db_save_execution_states(_EXECUTION_STATES, cfg):
            return

    path = _execution_states_file(config)
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(_EXECUTION_STATES, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception as exc:
        logger.warning(f"持久化工作流执行状态失败: {exc}")
        if tmp_path.exists():
            tmp_path.unlink()


_EXECUTION_STATES.update(_load_execution_states())

# ==================== Request / Response 模型 ====================


class WorkflowNode(BaseModel):
    id: str
    type: str
    title: str
    schemaKey: Optional[str] = None
    configValues: Dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: Optional[str] = None
    source: str
    target: str


class ExecuteRequest(BaseModel):
    workflowId: str = Field(..., description="工作流 ID")
    edges: List[WorkflowEdge] = Field(default_factory=list)
    nodes: List[WorkflowNode] = Field(default_factory=list, description="工作流节点配置")
    docs: List[str] = Field(default_factory=list, description="文档库文档 ID 列表")
    config: Dict[str, Any] = Field(default_factory=dict)
    localFiles: List[Dict[str, Any]] = Field(
        default_factory=list, description="本地上传文件 [{name, size, content(base64)}]"
    )
    sessionId: Optional[str] = Field(None, description="会话 ID（可选）")


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    progress: int = 0
    current_file_index: int = 0
    total_files: int = 0
    current_file_name: str = ""
    current_node_id: str = ""
    current_node_name: str = ""
    current_node_index: int = 0
    total_nodes: int = 0
    node_progress: List[Dict[str, Any]] = Field(default_factory=list)
    logs: List[Dict[str, str]] = Field(default_factory=list)
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    nodes: List[Dict[str, Any]]


# ==================== 辅助函数 ====================


def _get_output_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输出节点配置。优先「输出文件/文档库」节点，否则用第一个输出节点。"""
    first_output: Dict[str, Any] = {}
    for node in nodes:
        if node.type != "output":
            continue
        cv = dict(node.configValues or {})
        cv["_schemaKey"] = node.schemaKey
        if node.schemaKey == "schema-save-excel":
            cv.setdefault("outputFormat", "xlsx")
        elif node.schemaKey == "schema-save-text":
            cv.setdefault("outputFormat", "txt")
        if not first_output:
            first_output = cv
        # 画布上可能存在多个输出型节点时的歧义处理
        if node.schemaKey == "schema-library-output":
            return cv
        if node.schemaKey in {"schema-save-excel", "schema-save-text"}:
            return cv
    return first_output


def _normalize_output_format(value: Any) -> str:
    fmt = str(value or "").strip().lower()
    aliases = {
        "markdown": "md",
        "text": "txt",
        "plaintext": "txt",
        "plain_text": "txt",
        "excel": "xlsx",
        "xls": "xlsx",
    }
    return aliases.get(fmt, fmt)


def _infer_output_format_from_nodes(nodes: List[WorkflowNode]) -> str:
    for node in reversed(nodes):
        if node.schemaKey != "schema-convert-format":
            continue
        target_format = _normalize_output_format((node.configValues or {}).get("targetFormat"))
        if target_format in {"md", "txt", "pdf", "xlsx"}:
            return target_format
    return ""


def _resolve_output_format(output_config: Dict[str, Any], nodes: List[WorkflowNode]) -> str:
    configured_format = _normalize_output_format(output_config.get("outputFormat"))
    schema_key = str(output_config.get("_schemaKey") or "")
    inferred_format = _infer_output_format_from_nodes(nodes)

    if configured_format in {"pdf", "xlsx", "txt"}:
        return configured_format
    if configured_format == "md" and schema_key in {"schema-library-output", "schema-save", ""} and inferred_format in {"pdf", "xlsx", "txt"}:
        return inferred_format
    if configured_format == "md":
        return "md"
    return inferred_format or "md"


def _get_input_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输入节点配置。"""
    for node in nodes:
        if node.type == "input":
            return node.configValues or {}
    return {}


def _get_translation_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取翻译/AI节点配置。"""
    for node in nodes:
        if node.type in ("translate", "ai"):
            return node.configValues or {}
    return {"targetLanguage": "中文"}


def _get_run_config(config_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    source = dict(config_data or {})
    run = dict(source.get("run") or source)
    try:
        concurrent_limit = int(run.get("concurrentLimit", 4))
    except Exception:
        concurrent_limit = 4

    def _as_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    return {
        "concurrentLimit": max(1, min(concurrent_limit, 10)),
        "continueOnError": _as_bool(run.get("continueOnError"), False),
        "notifyOnError": _as_bool(run.get("notifyOnError"), True),
    }


def _get_processing_nodes(nodes: List[WorkflowNode]) -> List[WorkflowNode]:
    """从节点列表中提取所有处理节点（排除输入/输出节点）。"""
    processing = []
    for node in nodes:
        if node.type not in ("input", "output"):
            processing.append(node)
    return processing


def _normalize_workflow_edges(nodes: List[WorkflowNode], edges: Optional[List[WorkflowEdge]] = None) -> List[Dict[str, str]]:
    node_ids = [node.id for node in nodes if node.id]
    node_id_set = set(node_ids)
    normalized: List[Dict[str, str]] = []
    seen = set()

    if edges:
        for edge in edges:
            source = str(edge.source or "").strip()
            target = str(edge.target or "").strip()
            if not source or not target or source == target:
                continue
            if source not in node_id_set or target not in node_id_set:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"id": str(edge.id or f"e_{source}_{target}"), "source": source, "target": target})
        return normalized

    for source, target in zip(node_ids, node_ids[1:]):
        normalized.append({"id": f"e_{source}_{target}", "source": source, "target": target})
    return normalized


def _topological_node_ids(nodes: List[WorkflowNode], edges: Optional[List[WorkflowEdge]] = None) -> Tuple[List[str], List[str]]:
    node_ids = [node.id for node in nodes if node.id]
    if not node_ids:
        return [], []

    normalized_edges = _normalize_workflow_edges(nodes, edges)
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing = {node_id: [] for node_id in node_ids}
    for edge in normalized_edges:
        source = edge["source"]
        target = edge["target"]
        outgoing[source].append(target)
        indegree[target] += 1

    order_hint = {node_id: idx for idx, node_id in enumerate(node_ids)}
    ready = sorted([node_id for node_id, degree in indegree.items() if degree == 0], key=lambda x: order_hint[x])
    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current], key=lambda x: order_hint[x]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=lambda x: order_hint[x])

    if len(ordered) != len(node_ids):
        return [], ["工作流图结构不合法：检测到循环连线"]
    return ordered, []


def _validate_workflow_graph(nodes: List[WorkflowNode], edges: Optional[List[WorkflowEdge]] = None) -> List[str]:
    errors: List[str] = []
    node_ids = [node.id for node in nodes if node.id]
    node_id_set = set(node_ids)
    if len(node_ids) != len(node_id_set):
        return ["工作流图结构不合法：节点ID重复"]

    if edges:
        for edge in edges:
            source = str(edge.source or "").strip()
            target = str(edge.target or "").strip()
            if not source or not target:
                errors.append("工作流图结构不合法：连线缺少source或target")
            elif source == target:
                errors.append("工作流图结构不合法：节点不能连接自己")
            elif source not in node_id_set or target not in node_id_set:
                errors.append("工作流图结构不合法：连线指向不存在的节点")

    _, topo_errors = _topological_node_ids(nodes, edges)
    errors.extend(topo_errors)
    return errors


def _build_node_progress(nodes: List[WorkflowNode], edges: Optional[List[WorkflowEdge]] = None) -> List[Dict[str, Any]]:
    ordered_ids, _ = _topological_node_ids(nodes, edges)
    order_index = {node_id: idx for idx, node_id in enumerate(ordered_ids)}
    ordered_nodes = sorted(nodes, key=lambda node: order_index.get(node.id, len(order_index)))
    progress_items: List[Dict[str, Any]] = []
    for idx, node in enumerate(ordered_nodes, start=1):
        progress_items.append(
            {
                "id": node.id,
                "title": node.title,
                "type": node.type,
                "schemaKey": node.schemaKey,
                "index": idx,
                "status": "pending",
                "progress": 0,
                "message": "",
            }
        )
    return progress_items


def _validate_execute_request(request: ExecuteRequest) -> List[str]:
    errors: List[str] = []
    errors.extend(_validate_workflow_graph(request.nodes, request.edges))
    for idx, node in enumerate(request.nodes, start=1):
        schema_key = str(node.schemaKey or "").strip()
        cv = node.configValues or {}
        title = node.title or schema_key or f"第{idx}个节点"

        if schema_key == "schema-data-process":
            process_kind = str(cv.get("processKind") or "").strip()
            if process_kind not in {"sort", "filter", "aggregate", "dedupe", "fill_null", "computed_column", "merge_columns", "split_column"}:
                errors.append(f"{title}：processKind配置无效")
            required_by_kind = {
                "sort": ["sortColumn"],
                "filter": ["filterExpr"],
                "aggregate": ["aggregateColumn", "aggregateOp"],
                "fill_null": ["fillColumns"],
                "computed_column": ["computedColumnName", "computedFormula"],
                "merge_columns": ["mergeSourceColumns", "mergeTargetColumn"],
                "split_column": ["splitSourceColumn", "splitIntoColumns"],
            }
            missing = [key for key in required_by_kind.get(process_kind, []) if not str(cv.get(key) or "").strip()]
            if missing:
                errors.append(f"{title}：缺少配置 {', '.join(missing)}")
        elif schema_key == "schema-data-clean":
            rules = cv.get("cleanRules")
            if not rules:
                errors.append(f"{title}：cleanRules不能为空")
        elif schema_key == "schema-table-extract":
            strategy = str(cv.get("tableStrategy") or "first").strip()
            if strategy not in {"first", "all", "by_index"}:
                errors.append(f"{title}：tableStrategy配置无效")
            if strategy == "by_index":
                try:
                    if int(cv.get("tableIndex")) <= 0:
                        raise ValueError()
                except Exception:
                    errors.append(f"{title}：tableIndex必须是从1开始的正整数")
        elif schema_key == "schema-save-excel":
            sheet_name = str(cv.get("sheetName") or "Sheet1")
            if len(sheet_name) > 31:
                errors.append(f"{title}：sheetName不能超过31个字符")
            if any(ch in sheet_name for ch in '[]:*?/\\'):
                errors.append(f"{title}：sheetName不能包含 []:*?/\\")
        elif schema_key == "schema-save-text":
            encoding = str(cv.get("outputEncoding") or "utf-8").lower()
            if encoding not in {"utf-8", "gbk"}:
                errors.append(f"{title}：outputEncoding仅支持utf-8或gbk")
            line_ending = str(cv.get("lineEnding") or "lf").lower()
            if line_ending not in {"lf", "crlf"}:
                errors.append(f"{title}：lineEnding仅支持lf或crlf")

    return errors


# 语言 code → 人类可读名称映射
_LANG_MAP = {
    "en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语",
    "ar": "阿拉伯语", "pt": "葡萄牙语", "it": "意大利语",
    "zh-CN": "简体中文", "zh-TW": "繁体中文",
}


def _normalize_lang(code_or_label: str) -> str:
    """把语言 code 或 label 统一转为 label。"""
    if code_or_label in _LANG_MAP.values():
        return code_or_label
    return _LANG_MAP.get(code_or_label, code_or_label)


def _resolve_doc_path(doc_id: str, config: SystemConfig) -> Optional[Tuple[str, str]]:
    """根据文档 ID 解析磁盘路径，支持 session 文件和文档库文件。"""
    from db.library_repository import get_library_doc_by_id

    # 文档库文档
    doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
    if doc and doc.storage_key:
        p = Path(doc.storage_key)
        if p.exists():
            return str(p), str(doc.file_name or p.name)

    # session 文件
    parts = doc_id.split(":", 1)
    if len(parts) == 2 and parts[0] == "session":
        session_id, file_id = parts[1].split("/", 1)
        try:
            session = get_session_by_id(session_id, config=config)
            if session:
                for row in getattr(session, "files", []):
                    if str(row.id) == file_id:
                        p = Path(row.file_path)
                        if p.exists():
                            return str(p), str(row.file_name or p.name)
        except Exception:
            pass

    # 尝试 workspace 目录
    workspace_root = Path(config.work_dir)
    candidates = [
        workspace_root / doc_id,
        workspace_root / "uploads" / doc_id,
        workspace_root / "documents" / doc_id,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p), p.name
    return None


def _detect_file_type(name: str) -> FileType:
    """根据文件名推断 FileType。"""
    ext = Path(name).suffix.lower().lstrip(".")
    mapping = {
        "docx": FileType.DOCX,
        "pdf": FileType.PDF,
        "txt": FileType.TXT,
        "md": FileType.MD,
        "markdown": FileType.MD,
        "xlsx": FileType.XLSX,
        "xls": FileType.XLS,
        "csv": FileType.CSV,
        "doc": FileType.DOC,
    }
    return mapping.get(ext, FileType.TXT)


def _make_progress_callback(execution_id: str):
    """生成一个向执行状态写入进度日志的回调。"""

    def callback(progress: int, total: int, message: str, **kwargs):
        if execution_id not in _EXECUTION_STATES:
            return
        state = _EXECUTION_STATES[execution_id]
        file_index = int(state.get("current_file_index") or 1)
        total_files = max(int(state.get("total_files") or 1), 1)
        node_ratio = max(0.0, min(float(progress) / max(total, 1), 1.0))
        overall = int(((file_index - 1) + node_ratio) / total_files * 100)
        state["progress"] = max(0, min(overall, 99 if state.get("status") == "running" else 100))

        node_id = str(kwargs.get("node_id") or "")
        node_title = str(kwargs.get("node_title") or "")
        node_index = int(kwargs.get("node_index") or progress or 0)
        node_status = str(kwargs.get("node_status") or "running")
        node_item_progress = int(kwargs.get("node_progress") if kwargs.get("node_progress") is not None else (100 if node_status == "completed" else 50))

        if node_id or node_title:
            state["current_node_id"] = node_id
            state["current_node_name"] = node_title
            state["current_node_index"] = node_index
            state["total_nodes"] = max(int(state.get("total_nodes") or total or 0), int(total or 0))
            for item in state.get("node_progress", []):
                if (node_id and item.get("id") == node_id) or (not node_id and item.get("title") == node_title):
                    item["status"] = node_status
                    item["progress"] = max(0, min(node_item_progress, 100))
                    item["message"] = message
                    break
        state["logs"].append({"type": "info", "message": message})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states()

    return callback


def _make_concurrent_progress_callback_factory(execution_id: str, total_files: int, config: Optional[SystemConfig] = None):
    """Aggregate node progress from parallel file executions into one workflow state."""
    lock = threading.Lock()
    file_node_progress: Dict[Tuple[str, str], Dict[str, Any]] = {}
    total_files = max(int(total_files or 1), 1)

    def build_file_callback(file_name: str):
        def callback(progress: int, total: int, message: str, **kwargs):
            node_id = str(kwargs.get("node_id") or "")
            node_title = str(kwargs.get("node_title") or "")
            if not node_id and not node_title:
                return

            node_key = node_id or node_title
            node_index = int(kwargs.get("node_index") or progress or 0)
            node_status = str(kwargs.get("node_status") or "running")
            node_item_progress = int(
                kwargs.get("node_progress")
                if kwargs.get("node_progress") is not None
                else (100 if node_status == "completed" else 50)
            )
            node_item_progress = max(0, min(node_item_progress, 100))

            with lock:
                state = _EXECUTION_STATES.get(execution_id)
                if not state or state.get("status") != "running":
                    return

                file_node_progress[(file_name, node_key)] = {
                    "status": node_status,
                    "progress": node_item_progress,
                    "message": message,
                }

                completed_count = 0
                failed_count = 0
                running_count = 0
                progress_sum = 0
                for (_, seen_node), seen in file_node_progress.items():
                    if seen_node != node_key:
                        continue
                    status = seen.get("status")
                    item_progress = int(seen.get("progress") or 0)
                    progress_sum += item_progress
                    if status == "completed":
                        completed_count += 1
                    elif status == "failed":
                        failed_count += 1
                    else:
                        running_count += 1

                aggregate_progress = max(0, min(int(progress_sum / total_files), 100))
                if failed_count:
                    aggregate_status = "failed"
                    aggregate_progress = 100
                elif completed_count >= total_files:
                    aggregate_status = "completed"
                    aggregate_progress = 100
                elif running_count or completed_count:
                    aggregate_status = "running"
                else:
                    aggregate_status = "pending"

                state["current_node_id"] = node_id
                state["current_node_name"] = node_title
                state["current_node_index"] = node_index
                state["total_nodes"] = max(int(state.get("total_nodes") or total or 0), int(total or 0))

                for item in state.get("node_progress", []):
                    if (node_id and item.get("id") == node_id) or (not node_id and item.get("title") == node_title):
                        item["status"] = aggregate_status
                        item["progress"] = aggregate_progress
                        if aggregate_status == "completed":
                            item["message"] = f"已完成{completed_count}/{total_files}个文件"
                        elif aggregate_status == "failed":
                            item["message"] = f"{file_name}: {message}"
                        else:
                            item["message"] = f"{file_name}: {message}({completed_count}/{total_files})"
                        break

                node_items = state.get("node_progress", [])
                if node_items:
                    node_avg = int(sum(int(item.get("progress") or 0) for item in node_items) / len(node_items))
                    state["progress"] = max(
                        int(state.get("progress") or 0),
                        min(node_avg, 99 if state.get("status") == "running" else 100),
                    )

                state["logs"].append({"type": "info", "message": f"{file_name}: {message}"})
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_execution_states(config)

        return callback

    return build_file_callback


async def _run_execution(execution_id: str, params: ExecuteRequest):
    """
    后台执行任务：逐文件处理，支持本地文件和文档库文件。
    在 asyncio.to_thread 中运行，不阻塞事件循环。
    """
    config = get_config()
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        return

    try:
        output_config = _get_output_config(params.nodes)
        output_mode = output_config.get("outputMode", "download")
        output_format = _resolve_output_format(output_config, params.nodes)
        target_space_id = output_config.get("targetSpaceId")
        naming_rule = output_config.get("namingRule", "{original_name}_out")
        input_config = _get_input_config(params.nodes)
        run_config = _get_run_config(params.config)
        concurrent_limit = int(run_config["concurrentLimit"])
        continue_on_error = bool(run_config["continueOnError"])
        notify_on_error = bool(run_config["notifyOnError"])

        translation_config = _get_translation_config(params.nodes)
        target_language = _normalize_lang(translation_config.get("targetLanguage", "中文"))

        if str(output_mode).lower() == "library" and not target_space_id:
            state["logs"].append(
                {
                    "type": "warn",
                    "message": "输出模式为「保存到文档库」，但未选择目标文档库；文件只会生成在工作流输出目录，不会出现在文档库列表。请在输出节点选择目标库后重试。",
                }
            )
        elif str(output_mode).lower() == "library" and not (
            config.database.enabled and is_database_configured(config)
        ):
            state["logs"].append(
                {
                    "type": "warn",
                    "message": "文档库入库需要 PostgreSQL：请在 .env 中启用 DB_ENABLED 并配置 DATABASE_URL（或其它 DB_*）。当前数据库未就绪，仅能下载/查看本地输出路径。",
                }
            )

        # ===== 保存本地文件到磁盘 =====
        saved_local_files: List[Dict[str, Any]] = []  # [{path, name, size}]
        if params.localFiles:
            state["logs"].append({"type": "info", "message": f"正在上传 {len(params.localFiles)} 个本地文件..."})
            for lf in params.localFiles:
                name = lf.get("name", "unknown")
                content_bytes = lf.get("content") or lf.get("data")
                if not content_bytes:
                    state["logs"].append({"type": "warn", "message": f"  文件内容为空: {name}"})
                    continue
                if isinstance(content_bytes, str):
                    import base64 as _b64
                    try:
                        content_bytes = _b64.b64decode(content_bytes)
                    except Exception:
                        # 不是 base64，当作普通文本
                        content_bytes = content_bytes.encode("utf-8")
                upload_dir = Path(config.temp_dir) / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                safe_name = f"{uuid.uuid4().hex}_{Path(name).name}"
                file_path = upload_dir / safe_name
                file_path.write_bytes(content_bytes)
                saved_local_files.append({
                    "path": str(file_path),
                    "name": name,
                    "size": len(content_bytes),
                })
                state["logs"].append({"type": "done", "message": f"  已保存: {name}"})

        # ===== 收集源文件列表 =====
        source_files: List[FileInfo] = []

        # 从文档库
        for doc_id in params.docs:
            resolved_doc = _resolve_doc_path(doc_id, config)
            if resolved_doc:
                path, original_name = resolved_doc
                ft = _detect_file_type(original_name)
                source_files.append(FileInfo(path=path, file_type=ft, name=Path(original_name).name))
            else:
                state["logs"].append({"type": "warn", "message": f"文档路径未找到: {doc_id}"})

        # 从本地文件（已保存到磁盘）
        for lf in saved_local_files:
            ft = _detect_file_type(lf["name"])
            source_files.append(
                FileInfo(path=lf["path"], file_type=ft, name=lf["name"], metadata={"local": True, "size": lf["size"]})
            )

        # 也处理未上传的本地占位（跳过）
        for lf in params.localFiles:
            name = lf.get("name", "unknown")
            if not any(sf.name == name for sf in source_files):
                state["logs"].append({"type": "warn", "message": f"本地文件未上传，跳过: {name}"})

        if not source_files:
            state["status"] = "failed"
            state["error"] = "没有可处理的文件"
            state["error_code"] = "VALIDATION_ERROR"
            state["logs"].append({"type": "error", "message": "没有可处理的文件"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            return

        state["total_files"] = len(source_files)
        state["logs"].append({
            "type": "info",
            "message": f"运行设置：并发{concurrent_limit}，出错时{'继续' if continue_on_error else '停止'}",
        })
        state["logs"].append({"type": "info", "message": f"共 {len(source_files)} 个文件，开始处理..."})

        # ===== 逐文件处理 =====
        all_output_files: List[Dict[str, Any]] = []
        failed_count = 0
        failure_messages: List[str] = []
        coordinator = WorkflowCoordinator(config)

        if False and concurrent_limit > 1 and not continue_on_error:
            state["logs"].append({
                "type": "warn",
                "message": "已启用失败即停：为保证出错后立即停止，当前批次按顺序执行",
            })

        if concurrent_limit > 1 and len(source_files) > 1:
            state["logs"].append({
                "type": "info",
                "message": f"并发执行已启用：最多{concurrent_limit}个文档同时处理",
            })
            state["total_nodes"] = len(params.nodes)
            state["node_progress"] = _build_node_progress(params.nodes, params.edges)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            build_progress_callback = _make_concurrent_progress_callback_factory(
                execution_id,
                len(source_files),
                config,
            )

            def _build_task_spec(file_info: FileInfo) -> TaskSpec:
                return TaskSpec(
                    task_type=TaskType.WORKFLOW_PIPELINE,
                    instruction=f"workflow:{params.workflowId}",
                    source_files=[file_info],
                    session_id=params.sessionId,
                    parameters={
                        "workflow_nodes": [n.model_dump() for n in params.nodes],
                        "workflow_edges": [e.model_dump() for e in params.edges],
                        "output_config": {
                            "outputMode": output_mode,
                            "outputFormat": output_format,
                            "targetSpaceId": target_space_id,
                            "namingRule": naming_rule,
                            "targetLanguage": target_language,
                            "savePath": output_config.get("savePath"),
                            "sheetName": output_config.get("sheetName"),
                            "outputEncoding": output_config.get("outputEncoding"),
                            "lineEnding": output_config.get("lineEnding"),
                            "notifyOnComplete": output_config.get("notifyOnComplete"),
                        },
                        "input_config": input_config,
                        "execution_id": execution_id,
                    },
                )

            def _run_one_file(file_info: FileInfo) -> Dict[str, Any]:
                if not file_info.path or not Path(file_info.path).exists():
                    return {
                        "success": False,
                        "file": file_info.name,
                        "error": f"文件不存在: {file_info.name}",
                        "error_code": "SOURCE_FILE_MISSING",
                    }
                result = WorkflowCoordinator(config).execute(
                    _build_task_spec(file_info),
                    progress_callback=build_progress_callback(file_info.name),
                )
                if not result.success:
                    return {
                        "success": False,
                        "file": file_info.name,
                        "error": f"执行失败: {result.message}",
                        "error_code": "WORKFLOW_FAILED",
                    }
                output = result.data.get("output", {}) if isinstance(result.data, dict) else {}
                return {"success": True, "file": file_info.name, "output": output or {}}

            with ThreadPoolExecutor(max_workers=concurrent_limit) as pool:
                future_map = {}
                for idx, file_info in enumerate(source_files):
                    state["logs"].append({"type": "info", "message": f"[{idx + 1}/{len(source_files)}] 已提交: {file_info.name}"})
                    future_map[pool.submit(_run_one_file, file_info)] = file_info

                for completed, future in enumerate(as_completed(future_map), start=1):
                    file_info = future_map[future]
                    state["current_file_index"] = completed
                    state["current_file_name"] = file_info.name
                    state["progress"] = int(completed / len(source_files) * 100)
                    try:
                        item_result = future.result()
                    except Exception as exc:
                        item_result = {
                            "success": False,
                            "file": file_info.name,
                            "error": f"执行异常: {exc}",
                            "error_code": "WORKFLOW_FAILED",
                        }

                    if not item_result.get("success"):
                        msg = str(item_result.get("error") or f"处理失败: {file_info.name}")
                        failed_count += 1
                        failure_messages.append(msg)
                        state["logs"].append({"type": "error", "message": msg})
                        if notify_on_error:
                            state["logs"].append({"type": "warn", "message": f"错误通知：{file_info.name}处理失败"})
                        state["updated_at"] = datetime.now(timezone.utc).isoformat()
                        _persist_execution_states(config)
                        if not continue_on_error:
                            for pending in future_map:
                                if pending is not future:
                                    pending.cancel()
                            state["status"] = "failed"
                            state["error"] = msg
                            state["error_code"] = str(item_result.get("error_code") or "WORKFLOW_FAILED")
                            _persist_execution_states(config)
                            return
                        continue

                    out_item = item_result.get("output") or {}
                    if not out_item:
                        state["logs"].append({"type": "warn", "message": f"  无输出产物: {file_info.name}"})
                        state["updated_at"] = datetime.now(timezone.utc).isoformat()
                        _persist_execution_states(config)
                        continue

                    all_output_files.append(out_item)
                    out_path = out_item.get("path")
                    out_name = out_item.get("name", file_info.name)
                    state["logs"].append({"type": "done", "message": f"  已保存: {out_name}"})

                    if str(output_mode).lower() == "library" and out_path and target_space_id:
                        ok_lib, lib_msg = _save_output_to_library(str(out_path), str(target_space_id), config)
                        if ok_lib:
                            state["logs"].append({"type": "done", "message": f"  已保存到文档库: {out_name}"})
                        else:
                            state["logs"].append({"type": "error", "message": f"  文档库入库失败: {lib_msg}"})

                    state["updated_at"] = datetime.now(timezone.utc).isoformat()
                    _persist_execution_states(config)

            source_files = []

        for idx, file_info in enumerate(source_files):
            state["current_file_index"] = idx + 1
            state["current_file_name"] = file_info.name
            state["progress"] = int(idx / len(source_files) * 100)
            state["current_node_id"] = ""
            state["current_node_name"] = ""
            state["current_node_index"] = 0
            state["total_nodes"] = len(params.nodes)
            state["node_progress"] = _build_node_progress(params.nodes, params.edges)
            state["logs"].append(
                {"type": "info", "message": f"[{idx + 1}/{len(source_files)}] 正在处理: {file_info.name}"}
            )
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)

            if not file_info.path or not Path(file_info.path).exists():
                msg = f"文件不存在: {file_info.name}"
                failed_count += 1
                failure_messages.append(msg)
                state["logs"].append({"type": "error", "message": msg})
                if notify_on_error:
                    state["logs"].append({"type": "warn", "message": f"错误通知：{file_info.name}处理失败"})
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_execution_states(config)
                if not continue_on_error:
                    state["status"] = "failed"
                    state["error"] = msg
                    state["error_code"] = "SOURCE_FILE_MISSING"
                    _persist_execution_states(config)
                    return
                continue

            task_spec = TaskSpec(
                task_type=TaskType.WORKFLOW_PIPELINE,
                instruction=f"workflow:{params.workflowId}",
                source_files=[file_info],
                session_id=params.sessionId,
                parameters={
                    "workflow_nodes": [n.model_dump() for n in params.nodes],
                    "workflow_edges": [e.model_dump() for e in params.edges],
                    "output_config": {
                        "outputMode": output_mode,
                        "outputFormat": output_format,
                        "targetSpaceId": target_space_id,
                        "namingRule": naming_rule,
                        "targetLanguage": target_language,
                        "savePath": output_config.get("savePath"),
                        "sheetName": output_config.get("sheetName"),
                        "outputEncoding": output_config.get("outputEncoding"),
                        "lineEnding": output_config.get("lineEnding"),
                        "notifyOnComplete": output_config.get("notifyOnComplete"),
                    },
                    "input_config": input_config,
                    "execution_id": execution_id,
                },
            )
            wf_result = coordinator.execute(task_spec, progress_callback=_make_progress_callback(execution_id))
            if not wf_result.success:
                msg = f"执行失败: {wf_result.message}"
                failed_count += 1
                failure_messages.append(msg)
                state["logs"].append({"type": "error", "message": msg})
                if notify_on_error:
                    state["logs"].append({"type": "warn", "message": f"错误通知：{file_info.name}处理失败"})
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_execution_states(config)
                if not continue_on_error:
                    state["status"] = "failed"
                    state["error"] = str(wf_result.message)
                    state["error_code"] = "WORKFLOW_FAILED"
                    _persist_execution_states(config)
                    return
                continue

            out_item = {}
            if isinstance(wf_result.data, dict):
                out_item = wf_result.data.get("output", {}) or {}
            if not out_item:
                state["logs"].append({"type": "warn", "message": f"  无输出产物: {file_info.name}"})
                continue

            all_output_files.append(out_item)
            out_path = out_item.get("path")
            out_name = out_item.get("name", file_info.name)
            state["logs"].append({"type": "done", "message": f"  已保存: {out_name}"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)

            if str(output_mode).lower() == "library" and out_path:
                if target_space_id:
                    ok_lib, lib_msg = _save_output_to_library(str(out_path), str(target_space_id), config)
                    if ok_lib:
                        state["logs"].append({"type": "done", "message": f"  已保存到文档库: {out_name}"})
                    else:
                        state["logs"].append({"type": "error", "message": f"  文档库入库失败: {lib_msg}"})
                # 未选目标库时在任务开头已有 warn，此处不再重复

        # ===== 完成 =====
        state["progress"] = 100
        state["output_files"] = all_output_files
        if all_output_files:
            state["status"] = "completed"
            state["error"] = None
            state["error_code"] = None
            state["logs"].append({"type": "done", "message": f"全部完成，已处理 {len(all_output_files)} 个输出文件"})
            if output_config.get("notifyOnComplete"):
                state["logs"].append({"type": "done", "message": "完成通知：工作流已执行完成"})
            if failed_count > 0:
                state["logs"].append({"type": "warn", "message": f"其中 {failed_count} 个文件处理失败"})
        else:
            state["status"] = "failed"
            state["error_code"] = "WORKFLOW_FAILED"
            merged = "；".join(failure_messages[-3:]) if failure_messages else "全部文件处理失败"
            state["error"] = merged
            state["logs"].append({"type": "error", "message": f"执行失败: {merged}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    except Exception as e:
        logger.error(f"执行任务异常: {e}")
        state["status"] = "failed"
        state["error"] = str(e)
        state["error_code"] = "INTERNAL_ERROR"
        state["logs"].append({"type": "error", "message": f"执行异常: {e}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)


def _save_output_to_library(file_path: str, space_id: str, config: SystemConfig) -> Tuple[bool, str]:
    """将输出文件保存到文档库（写存储 + PostgreSQL 登记）。返回 (是否成功, 错误说明)。"""
    if not (config.database.enabled and is_database_configured(config)):
        return False, "数据库未启用或未配置，无法写入 library_documents"

    try:
        from db.library_repository import add_library_doc, get_library_space_by_id
        import hashlib

        p = Path(file_path)
        if not p.is_file():
            return False, f"输出文件不存在: {file_path}"

        # 与手动上传一致：登记为空间所属用户，否则已登录用户列表会带 user_id 条件，看不到 user_id 为空的记录
        space_row = get_library_space_by_id(space_id, config=config, user_id=None)
        owner_user_id = space_row.user_id if space_row else None

        with open(p, "rb") as f:
            content_bytes = f.read()
        file_size = len(content_bytes)
        file_hash = hashlib.md5(content_bytes).hexdigest()
        safe_name = f"{file_hash}_{p.name}"

        storage_key: Optional[str] = None
        if config.storage.enabled and config.storage.provider == "azure_blob":
            from core.storage import build_blob_name, upload_stream_to_storage
            from io import BytesIO

            blob_name = build_blob_name(space_id, safe_name, prefix=config.storage.azure_blob_prefix or "workflows")
            storage_key = upload_stream_to_storage(
                BytesIO(content_bytes),
                config=config,
                blob_name=blob_name,
                content_type="application/octet-stream",
            )
        else:
            upload_dir = Path(config.work_dir) / "library" / space_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            storage_key = str(upload_dir / safe_name)
            Path(storage_key).write_bytes(content_bytes)

        add_library_doc(
            space_id=space_id,
            file_name=p.name,
            file_size=file_size,
            config=config,
            user_id=owner_user_id,
            mime_type="application/octet-stream",
            storage_key=storage_key,
            blob_url=storage_key,
        )
        return True, ""
    except Exception as e:
        logger.warning(f"保存到文档库失败: {e}")
        return False, str(e)


# ==================== API 端点 ====================

# ⚠️ 路由顺序很重要：精确路径必须在动态路径 {workflow_id} 之前注册


@router.post("/execute", response_model=Dict[str, str])
async def execute_workflow(request: ExecuteRequest):
    """
    启动工作流执行（逐文件处理）。
    立即返回 execution_id，前端通过 GET /executions/{id} 轮询进度。
    """
    validation_errors = _validate_execute_request(request)
    if validation_errors:
        message = "；".join(validation_errors)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {"message": message, "code": "VALIDATION_ERROR"},
                "detail": message,
            },
        )

    execution_id = uuid.uuid4().hex

    _EXECUTION_STATES[execution_id] = {
        "status": "running",
        "progress": 0,
        "current_file_index": 0,
        "total_files": 0,
        "current_file_name": "",
        "current_node_id": "",
        "current_node_name": "",
        "current_node_index": 0,
        "total_nodes": len(request.nodes),
        "node_progress": _build_node_progress(request.nodes, request.edges),
        "logs": [{"type": "info", "message": "任务已启动，正在初始化..."}],
        "output_files": [],
        "error": None,
        "error_code": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # 后台运行，不阻塞 HTTP 响应。
    # _run_execution 内部包含文件读写、LLM/执行器等同步耗时逻辑；放到独立线程里，
    # 让前端能立即拿到 execution_id 并开始轮询节点进度。
    threading.Thread(
        target=lambda: asyncio.run(_run_execution(execution_id, request)),
        daemon=True,
    ).start()

    return {"execution_id": execution_id}


# -------- 精确路径端点（必须在 /{workflow_id} 之前） --------


@router.get("/templates")
async def list_templates():
    """返回内置工作流模板列表（节点含 schemaKey + configValues 默认值）。"""
    return {"templates": [
        {
            "id": "translate-pdf",
            "name": "PDF 翻译",
            "description": "将 PDF 文件翻译为目标语言",
            "nodes": [
                {
                    "id": "n_pdf_input",
                    "type": "input",
                    "title": "PDF 输入",
                    "icon": "📕",
                    "body": "导入 PDF 文件",
                    "schemaKey": "schema-pdf-input",
                    "configValues": {
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    }
                },
                {
                    "id": "n_ai_translate",
                    "type": "ai",
                    "title": "AI 翻译",
                    "icon": "🌍",
                    "body": "使用大模型进行智能翻译处理",
                    "schemaKey": "schema-translate",
                    "configValues": {
                        "targetLanguage": "en",
                        "prompt": "请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。",
                    }
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "输出文件",
                    "icon": "📁",
                    "body": "保存结果到文档库或直接下载",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "download",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_translated",
                        "outputFormat": "pdf",
                        "notifyOnComplete": True,
                    }
                },
            ],
        },
        {
            "id": "translate-docx",
            "name": "Word 翻译",
            "description": "将 Word 文档翻译为目标语言",
            "nodes": [
                {
                    "id": "n_docx_input",
                    "type": "input",
                    "title": "DOCX 输入",
                    "icon": "📘",
                    "body": "导入 Word 文档",
                    "schemaKey": "schema-docx-input",
                    "configValues": {
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    }
                },
                {
                    "id": "n_ai_translate",
                    "type": "ai",
                    "title": "AI 翻译",
                    "icon": "🌍",
                    "body": "使用大模型进行智能翻译处理",
                    "schemaKey": "schema-translate",
                    "configValues": {
                        "targetLanguage": "en",
                        "prompt": "请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。",
                    }
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "输出文件",
                    "icon": "📁",
                    "body": "保存结果到文档库或直接下载",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "download",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_translated",
                        "outputFormat": "md",
                        "notifyOnComplete": True,
                    }
                },
            ],
        },
    ]}


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    """获取指定模板的完整配置。"""
    templates_resp = await list_templates()
    templates = templates_resp.get("templates", []) if isinstance(templates_resp, dict) else []
    for t in templates:
        if t["id"] == template_id:
            return t
    raise HTTPException(status_code=404, detail="模板不存在")


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution_status(execution_id: str):
    """查询工作流执行状态。"""
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    error_code = state.get("error_code")
    if not error_code and state.get("status") == "failed":
        error_text = str(state.get("error") or "")
        if "没有可处理的文件" in error_text or "缺少" in error_text:
            error_code = "VALIDATION_ERROR"
        else:
            error_code = "WORKFLOW_FAILED"
    return ExecutionResponse(
        execution_id=execution_id,
        status=state["status"],
        progress=state["progress"],
        current_file_index=state["current_file_index"],
        total_files=state["total_files"],
        current_file_name=state["current_file_name"],
        current_node_id=state.get("current_node_id", ""),
        current_node_name=state.get("current_node_name", ""),
        current_node_index=state.get("current_node_index", 0),
        total_nodes=state.get("total_nodes", 0),
        node_progress=state.get("node_progress", []),
        logs=state["logs"],
        output_files=state["output_files"],
        error=state["error"],
        error_code=error_code,
    )


@router.get("/models", response_model=List[Dict[str, str]])
async def list_models():
    """返回可用 LLM 模型列表。"""
    return [
        {"id": "deepseek-chat", "name": "DeepSeek Chat"},
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet"},
    ]


@router.get("/languages", response_model=List[Dict[str, str]])
async def list_languages():
    """返回支持的目标语言列表。"""
    return [
        {"code": "zh", "name": "中文"},
        {"code": "en", "name": "English"},
        {"code": "ja", "name": "日本語"},
        {"code": "ko", "name": "한국어"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "es", "name": "Español"},
        {"code": "ru", "name": "Русский"},
        {"code": "ar", "name": "العربية"},
        {"code": "pt", "name": "Português"},
    ]


@router.get("/output-formats", response_model=List[Dict[str, str]])
async def list_output_formats():
    """返回支持的输出格式列表。"""
    return [
        {"code": "pdf", "name": "PDF"},
        {"code": "md", "name": "Markdown"},
        {"code": "txt", "name": "纯文本"},
        {"code": "xlsx", "name": "Excel"},
    ]


# -------- 用户工作流 CRUD（/{workflow_id} 必须在最后） --------


class SaveWorkflowRequest(BaseModel):
    id: str = Field(..., description="工作流 ID（唯一标识，新建时由前端生成）")
    name: str = Field(..., description="工作流名称")
    icon: str = Field("🔧", description="图标 emoji")
    type: str = Field("custom", description="类型（custom/template）")
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="节点列表（含 configValues 等完整配置）"
    )
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict, description="全局配置")


@router.get("", response_model=Dict[str, Any])
async def list_user_workflows():
    """返回用户自定义工作流列表（不含模板）。"""
    return {"workflows": list_workflows()}


@router.post("", response_model=Dict[str, Any])
async def save_user_workflow(request: SaveWorkflowRequest):
    """保存（新建或更新）用户工作流。"""
    if request.type == "template":
        raise HTTPException(status_code=400, detail="模板工作流不可通过此接口保存")
    config_data = dict(request.config or {})
    config_data["edges"] = request.edges or []
    wf = save_workflow(
        workflow_id=request.id,
        name=request.name,
        icon=request.icon,
        nodes=request.nodes,
        config_data=config_data,
        edges=request.edges,
    )
    return wf


@router.get("/{workflow_id}", response_model=Dict[str, Any])
async def get_single_workflow(workflow_id: str):
    """获取指定工作流的完整配置（含节点和 config）。"""
    wf = get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


@router.delete("/{workflow_id}", response_model=Dict[str, bool])
async def delete_user_workflow(workflow_id: str):
    """删除指定用户工作流。"""
    success = delete_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="工作流不存在或为模板工作流")
    return {"success": True}
