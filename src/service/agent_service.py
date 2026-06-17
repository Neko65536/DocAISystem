"""Agent 服务层 - 封装现有 Agent 供 API 调用"""
from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from config import SystemConfig, get_config
from core.llm import get_llm_service
from core.storage import download_file_to_local
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import TaskSpec, TaskType, FileInfo, FileType
from db.session_repository import get_messages, get_session_files
from utils.output_naming import output_filename_from_source
from langchain_openai import ChatOpenAI
from service.intent_router import IntentRouter

# ============================================================================
# Session 级别的 Agent 实例缓存
# 设计原则：文件和对话历史都跟随消息，agent 被同一个 session 复用
# ============================================================================
_agent_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _get_cached_agent(session_id: str, config: SystemConfig) -> Any:
    """
    获取或创建 session 对应的 DocumentAgent 实例。
    该实例在同一 session 的多次对话中被复用，对话历史累积。
    """
    with _cache_lock:
        if session_id not in _agent_cache:
            from core.agents.document_understand_agent import DocumentAgent
            _agent_cache[session_id] = DocumentAgent(config)
        return _agent_cache[session_id]


def clear_session_agent(session_id: str):
    """清除 session 对应的 agent 实例（当需要重置时调用）"""
    with _cache_lock:
        if session_id in _agent_cache:
            del _agent_cache[session_id]


def _resolve_local_file_path(file_dict: Dict[str, Any], config: SystemConfig, session_id: str = None) -> str:
    """把 storage_key 解析为可被本地 Agent 读取的临时文件路径。"""
    storage_key = str(file_dict.get("storage_key") or "").strip()
    if not storage_key:
        return ""

    file_name = str(file_dict.get("file_name") or storage_key).strip() or storage_key
    cache_dir = Path(config.temp_dir) / "file_cache" / (session_id or "shared")
    cache_path = cache_dir / file_name
    if cache_path.exists():
        return str(cache_path)

    try:
        return str(download_file_to_local(storage_key, cache_path, config=config))
    except Exception:
        pass

    # 本地临时文件路径检查：先尝试直接路径，再尝试相对路径
    storage_path = Path(storage_key)
    if storage_path.is_absolute() and storage_path.exists():
        return str(storage_path)

    project_root = Path(__file__).resolve().parents[2]
    work_dir = Path(str(getattr(config, "work_dir", "workspace") or "workspace"))
    normalized_key = storage_key.replace("\\", "/")
    normalized_work_dir = work_dir.as_posix().strip("/")
    project_candidates = [project_root / storage_key]
    if normalized_work_dir and not normalized_key.startswith(f"{normalized_work_dir}/"):
        project_candidates.append(project_root / work_dir / storage_key)
    for candidate in project_candidates:
        if candidate.exists():
            return str(candidate)

    # 尝试相对于项目根目录的路径
    upload_dir = Path("workspace/uploads")
    relative_path = upload_dir / storage_key if not str(storage_key).startswith(str(upload_dir)) else storage_path
    if relative_path.exists():
        return str(relative_path)

    # 如果文件存在于缓存目录的子目录中
    if session_id:
        session_cache_dir = cache_dir.parent / session_id
        if session_cache_dir.exists():
            for f in session_cache_dir.rglob("*"):
                if f.is_file() and f.name == file_name:
                    return str(f)

    # 返回原始路径，让调用方处理错误
    return storage_key


def set_agent_files(agent: Any, files: List[Dict[str, Any]], config: SystemConfig, session_id: str = None):
    """
    将消息携带的文件设置到 agent。
    设计：每次消息的文件都追加/更新到 agent，不清除旧文件。
    这样用户可以问"基于刚才的文件"或"基于所有上传的文件"。
    
    重要：如果 files 为空列表（表示用户主动取消了所有文件勾选），
    则清除 agent 的文档内容，防止使用旧文档产生幻觉。
    """
    # ========== 核心修复：无文件时清除 agent 的文档内容 ==========
    if not files:
        # 用户没有勾选任何文件，清除 agent 的文档缓存
        agent._document_contents = {}
        agent._source_files = []
        return
    
    file_infos = []
    for f in files:
        is_selected = f.get('is_selected', True)
        if not is_selected:
            continue
        file_path = _resolve_local_file_path(f, config, session_id)
        if not file_path and session_id and f.get('file_id'):
            db_files = get_session_files(session_id, config=config)
            for db_file in db_files:
                if db_file.id == f.get('file_id'):
                    file_path = _resolve_local_file_path(
                        {
                            "storage_key": getattr(db_file, "storage_key", None),
                            "file_name": getattr(db_file, "file_name", ""),
                        },
                        config,
                        session_id,
                    )
                    break
        
        file_info = FileInfo(
            path=file_path,
            file_type=_get_file_type(f.get('file_name', '')),
        )
        file_infos.append(file_info)
    
    if file_infos:
        # 调用 agent 的 set_documents 方法加载文件
        agent.set_documents(file_infos, max_rows=100)


def _get_file_type(file_name: str) -> FileType:
    """根据文件名判断文件类型"""
    ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
    mapping = {
        'pdf': FileType.PDF,
        'doc': FileType.DOCX,
        'docx': FileType.DOCX,
        'xls': FileType.XLSX,
        'xlsx': FileType.XLSX,
        'txt': FileType.TXT,
        'md': FileType.MD,
    }
    return mapping.get(ext, FileType.TXT)


def get_selected_session_files_payload(
    session_id: str, config: SystemConfig
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    从会话存储读取已勾选的数据文件与模板，组装为 Agent 所需的字典列表。
    前端发消息时未带 file_path，须以库中勾选状态为准。
    """
    rows = get_session_files(session_id, config=config)
    data_files: List[Dict[str, Any]] = []
    template_files: List[Dict[str, Any]] = []
    for f in rows:
        if not getattr(f, "is_selected", False):
            continue
        entry = {
            "storage_key": getattr(f, "storage_key", None),
            "file_name": f.file_name,
            "is_selected": True,
        }
        if f.file_type == "data":
            data_files.append(entry)
        elif f.file_type == "template":
            template_files.append(entry)
    return data_files, template_files


class AgentService:
    """Agent 服务封装 - 接入现有 Agent"""

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.coordinator = WorkflowCoordinator(self.config)
        self.intent_router = IntentRouter()

    def resolve_effective_mode(
        self,
        mode: str,
        content: str,
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """默认对话下先做结构化意图路由，再进入对应任务链路。"""
        route = self.intent_router.resolve(mode, content, files or [], template_files or [])
        return route.mode

    def _document_editing_user_message(self, result: Any) -> str:
        if not result:
            return "文档编辑完成"
        if not bool(getattr(result, "success", False)):
            return self.to_user_visible_message("document_editing", getattr(result, "message", "") or "文档编辑失败")
        return "文档编辑完成，已生成可下载文件"

    def to_user_visible_message(self, mode: str, message: Any) -> str:
        text = str(message or "").strip()
        if not text:
            if mode == "document_editing":
                return "文档编辑完成"
            return ""

        if mode == "document_editing":
            if re.search(r"Agent[_ ]?A.*执行完成|agent_a.*执行完成", text, flags=re.IGNORECASE):
                return "文档编辑完成，已生成可下载文件"
            if "Agent_A最小骨架" in text or "最小骨架" in text:
                return "文档编辑任务已处理"
            if "缺少生成指令" in text:
                return "文档编辑失败：未能识别需要写入文档的新内容，请把要生成或追加的内容要求描述得更明确。"
            text = re.sub(r"\bAgent[_ ]?A\b", "文档编辑模块", text, flags=re.IGNORECASE)
            text = re.sub(r"\bagent_a\b", "文档编辑模块", text, flags=re.IGNORECASE)
        return text

    async def _stream_sync_generator(self, gen):
        """
        将同步生成器包装为异步生成器，逐项 yield。
        用于在异步上下文中使用 DocumentAgent 的 stream_chat()。
        关键：必须在后台线程中运行同步生成器，否则会阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        def get_next():
            try:
                return next(gen)
            except StopIteration:
                return None
        while True:
            item = await loop.run_in_executor(None, get_next)
            if item is None:
                break
            yield item

    async def _get_document_agent(
        self,
        session_id: str,
        content: str,
        files: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        获取缓存的 DocumentAgent 实例，并将消息携带的文件设置到 agent。
        设计：agent 被 session 复用，对话历史累积；文件跟随消息追加到 agent。
        """
        # 获取或创建缓存的 agent 实例
        agent = _get_cached_agent(session_id, self.config)
        
        # 将消息携带的文件设置到 agent（传入 session_id 以便从数据库查询 file_path）
        if files:
            set_agent_files(agent, files, self.config, session_id)
        
        return agent

    async def chat_stream(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
        progress_callback=None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天响应。
        每次对话都基于当前勾选的文件，支持多轮对话上下文。
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = str(mode).strip()
        mode = self.resolve_effective_mode(mode, content, files or [], template_files)

        # 默认对话：直连 LLM 流式
        if mode == "default_conversation":
            async for part in self._stream_default_conversation(session_id):
                yield part
            return

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            async for part in self._stream_sync_generator(agent.stream_chat(content)):
                yield part
            return

        # 文档编辑模式：走工作流协调器，进入 AgentA 真实编辑链路
        if mode == "document_editing":
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
            result = await asyncio.to_thread(self.coordinator.execute, task_spec, progress_callback=progress_callback)
            await asyncio.sleep(0)

            message = self._document_editing_user_message(result)
            for char in message:
                yield char
                await asyncio.sleep(0.005)
            return

        # 实体提取模式：返回完整 JSON（非流式），支持进度回调
        if mode == "entity_extraction":
            import json
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)

            result = await asyncio.to_thread(
                self.coordinator.execute,
                task_spec,
                progress_callback=progress_callback,
            )
            await asyncio.sleep(0)

            if mode == "entity_extraction":
                agent_response = result.data if result and result.data else None
                inner_data = agent_response.data if agent_response else {}
                response_data = {
                    "success": result.success if result else False,
                    "message": result.message if result else "实体提取失败",
                    "entities": inner_data.get("entities") if isinstance(inner_data, dict) else [],
                    "schema": inner_data.get("schema") if isinstance(inner_data, dict) else {},
                    "chunk_count": inner_data.get("chunk_count") if isinstance(inner_data, dict) else 0,
                    "total_extractions": inner_data.get("total_extractions") if isinstance(inner_data, dict) else 0,
                }
                yield json.dumps(response_data, ensure_ascii=False)
                return

        # 表格填表模式：返回结构化 JSON（非流式）
        if mode == "table_filling":
            import json
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)

            result = await asyncio.to_thread(
                self.coordinator.execute,
                task_spec,
                progress_callback=progress_callback,
            )
            await asyncio.sleep(0)

            agent_response = result.data if result and result.data else None
            inner_data = agent_response.data if agent_response else {}
            response_data = {
                "success": result.success if result else False,
                "message": result.message if result else "表格填表失败",
                "status": inner_data.get("status") if isinstance(inner_data, dict) else "completed",
                "excel_path": inner_data.get("excel_path") if isinstance(inner_data, dict) else None,
                "output_json": inner_data.get("output_json") if isinstance(inner_data, dict) else None,
                "total_rows": inner_data.get("total_rows") if isinstance(inner_data, dict) else 0,
                "matched_rows": inner_data.get("matched_rows") if isinstance(inner_data, dict) else 0,
                "used_plan": inner_data.get("used_plan") if isinstance(inner_data, dict) else None,
                "plan_source": inner_data.get("plan_source") if isinstance(inner_data, dict) else None,
                "template_filled": inner_data.get("template_filled") if isinstance(inner_data, dict) else False,
                "template_output": inner_data.get("template_output") if isinstance(inner_data, dict) else None,
                "template_mapping": inner_data.get("template_mapping") if isinstance(inner_data, dict) else {},
                "multi_table_results": inner_data.get("multi_table_results") if isinstance(inner_data, dict) else None,
            }
            yield json.dumps(response_data, ensure_ascii=False)
            return

        # 其他模式：模拟流式输出
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = self.coordinator.execute(task_spec)

        visible_message = self.to_user_visible_message(mode, result.message)
        for char in visible_message:
            yield char
            await asyncio.sleep(0.005)

    async def chat(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        非流式聊天响应
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = str(mode).strip()
        mode = self.resolve_effective_mode(mode, content, files or [], template_files)

        # 默认对话
        if mode == "default_conversation":
            return await self._get_conversation_response(session_id)

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            return agent.chat(content)

        if mode == "document_editing":
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
            result = await asyncio.to_thread(self.coordinator.execute, task_spec)
            return self._document_editing_user_message(result)

        # 其他模式
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = self.coordinator.execute(task_spec)
        return self.to_user_visible_message(mode, result.message)

    async def _get_conversation_response(self, session_id: str) -> str:
        """获取默认对话的完整回复（非流式）"""
        llm = get_llm_service()
        if not llm.is_available():
            return "LLM 服务不可用，请检查 API Key 配置。"

        # 直接传字典列表，llm.chat 内部会进行转换
        messages = self._build_conversation_llm_messages(session_id)
        return llm.chat(messages=messages)

    def _get_task_type(self, mode: str) -> TaskType:
        """将前端模式转换为 TaskType"""
        mapping = {
            "default_conversation": TaskType.DEFAULT_CONVERSATION,
            "document_understanding": TaskType.DOCUMENT_UNDERSTANDING,
            "document_editing": TaskType.DOCUMENT_EDITING,
            "entity_extraction": TaskType.ENTITY_EXTRACTION,
            "table_filling": TaskType.TABLE_FILLING,
        }
        return mapping.get(mode, TaskType.DEFAULT_CONVERSATION)

    def _get_file_type(self, file_name: str) -> FileType:
        """根据文件名判断文件类型"""
        ext = file_name.lower().split('.')[-1]
        mapping = {
            'pdf': FileType.PDF,
            'doc': FileType.DOCX,
            'docx': FileType.DOCX,
            'xls': FileType.XLSX,
            'xlsx': FileType.XLSX,
            'txt': FileType.TXT,
            'md': FileType.MD,
        }
        return mapping.get(ext, FileType.TXT)

    def _build_file_info(self, file_dict: Dict[str, Any], session_id: Optional[str] = None) -> FileInfo:
        """将文件字典转换为 FileInfo"""
        file_name = str(file_dict.get("file_name") or file_dict.get("name") or "").strip()
        storage_key = str(file_dict.get("storage_key") or file_dict.get("file_path") or file_dict.get("path") or "").strip()
        if not file_name:
            file_name = Path(storage_key).name if storage_key else "unnamed"
        return FileInfo(
            path=_resolve_local_file_path(file_dict, self.config, session_id),
            file_type=self._get_file_type(file_name),
            name=Path(file_name).name,
            size=int(file_dict.get("file_size") or file_dict.get("size") or 0),
            metadata={"storage_key": storage_key},
        )

    def _build_task_spec(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskSpec:
        """构建任务规格"""
        # 获取数据文件
        source_files = [self._build_file_info(f, session_id) for f in files if f.get('is_selected', True)]
        output_file = None
        if mode == "document_editing" and source_files:
            editable_file = next(
                (
                    f for ext in ("docx", "md", "txt", "xlsx")
                    for f in source_files
                    if f.file_type.value.lower() == ext
                ),
                source_files[0],
            )
            source_path = Path(editable_file.path)
            output_dir = Path(self.config.output_dir) / "chat_edits" / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            source_name = editable_file.name or source_path.name
            output_format = Path(source_name).suffix or source_path.suffix or editable_file.file_type.value
            output_file = str(output_dir / output_filename_from_source(source_name, output_format))
        elif mode == "entity_extraction" and source_files:
            source_path = Path(source_files[0].name or source_files[0].path)
            output_dir = Path(self.config.output_dir) / "chat_entity_extraction" / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = str(output_dir / output_filename_from_source(source_path.name, "json"))

        # 获取模板文件
        template_file = None
        if template_files:
            selected_templates = [f for f in template_files if f.get('is_selected', True)]
            if selected_templates:
                template_file = self._build_file_info(selected_templates[0], session_id)

        return TaskSpec(
            task_type=self._get_task_type(mode),
            instruction=content,
            source_files=source_files,
            template_file=template_file,
            output_file=output_file,
            session_id=session_id,
        )

    def _build_conversation_llm_messages(self, session_id: str) -> List[Dict[str, str]]:
        """默认对话：从会话历史构造发给 LLM 的消息列表（含刚写入的用户消息）。"""
        system_prompt = get_config().agent.get_prompt("conversation")
        rows = get_messages(session_id, limit=50, config=self.config)
        msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for r in rows:
            if r.role in ("user", "assistant"):
                msgs.append({"role": r.role, "content": r.content})
        return msgs

    async def _stream_default_conversation(self, session_id: str) -> AsyncGenerator[str, None]:
        """默认对话：真实 LLM 流式输出，保留 Markdown 原文。"""
        llm = get_llm_service()
        if not llm.is_available():
            yield "LLM 服务不可用，请检查 API Key 配置。"
            return

        lc_messages = llm._convert_messages(self._build_conversation_llm_messages(session_id))
        client = ChatOpenAI(
            api_key=llm._get_api_key(),
            base_url=llm._get_base_url(),
            model=llm.config.model,
            temperature=llm.config.temperature,
            max_tokens=llm.config.max_tokens,
            streaming=True,
        )
        def _chunk_to_text(chunk) -> str:
            raw = getattr(chunk, "content", None) or ""
            if isinstance(raw, str):
                return raw
            if isinstance(raw, list):
                parts = []
                for block in raw:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return "".join(parts)
            return str(raw)

        stream_iter = client.stream(lc_messages)
        while True:
            chunk = await asyncio.to_thread(next, stream_iter, None)
            if chunk is None:
                break
            text = _chunk_to_text(chunk)
            if text:
                yield text

    def execute_task(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        执行 Agent 任务（非流式）
        """
        task_spec = self._build_task_spec(session_id, mode, content, files, template_files)
        result = self.coordinator.execute(task_spec)

        # 表格填表模式：返回结构化字典
        if mode == "table_filling":
            agent_response = result.data if result.data else None
            inner_data = agent_response.data if agent_response else {}
            return {
                "success": result.success,
                "message": result.message,
                "status": inner_data.get("status") if isinstance(inner_data, dict) else "completed",
                "excel_path": inner_data.get("excel_path") if isinstance(inner_data, dict) else None,
                "output_json": inner_data.get("output_json") if isinstance(inner_data, dict) else None,
                "total_rows": inner_data.get("total_rows") if isinstance(inner_data, dict) else 0,
                "matched_rows": inner_data.get("matched_rows") if isinstance(inner_data, dict) else 0,
                "used_plan": inner_data.get("used_plan") if isinstance(inner_data, dict) else None,
                "plan_source": inner_data.get("plan_source") if isinstance(inner_data, dict) else None,
                "template_filled": inner_data.get("template_filled") if isinstance(inner_data, dict) else False,
                "template_output": inner_data.get("template_output") if isinstance(inner_data, dict) else None,
                "template_mapping": inner_data.get("template_mapping") if isinstance(inner_data, dict) else {},
                "multi_table_results": inner_data.get("multi_table_results") if isinstance(inner_data, dict) else None,
            }

        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "output_file": result.output_file,
        }
