"""
浠诲姟鎵ц鍣?
璐熻矗璋冪敤Agent鎵ц鍏蜂綋浠诲姟
鏂囨。瑙ｆ瀽鐢卞悇Agent鑷澶勭悊锛堜娇鐢ㄥ閮ㄥ簱濡俻ython-docx, pdfplumber绛夛級
"""
from typing import Optional, List, Any, Dict, Tuple
import csv
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from config import SystemConfig, get_config
from core.storage import build_blob_name, upload_file_to_storage
from utils.logger import get_logger
from utils.output_naming import output_filename_from_source
from core.orchestrator.task_spec import FileInfo, TaskSpec


class TaskExecutor:
    """
    浠诲姟鎵ц鍣?
    灏佽Agent鐨勮皟鐢ㄩ€昏緫
    娉ㄦ剰锛氭枃妗ｈВ鏋愮敱鍚凙gent鑷澶勭悊锛屼笉浣跨敤缁熶竴鐨勮В鏋愬櫒
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        self._agents = {}
        self._file_cache: Dict[str, Any] = {}  # 缂撳瓨宸茶В鏋愮殑鏂囦欢鍐呭

    def get_file_content(self, file_info: FileInfo) -> Any:
        """
        鑾峰彇鏂囦欢鍐呭
        鐢卞悇Agent鑷瀹炵幇鍏蜂綋瑙ｆ瀽閫昏緫
        """
        if file_info.path in self._file_cache:
            return self._file_cache[file_info.path]

        self.logger.info(f"读取文件: {file_info.name}")
        # 鍏蜂綋瑙ｆ瀽閫昏緫鐢盇gent瀹炵幇锛岃繖閲屽彧杩斿洖鏂囦欢璺緞
        return file_info.path

    def cache_file_content(self, file_path: str, content: Any):
        """缂撳瓨鏂囦欢瑙ｆ瀽缁撴灉"""
        self._file_cache[file_path] = content

    def clear_cache(self):
        """娓呴櫎鏂囦欢缂撳瓨"""
        self._file_cache.clear()

    def parse_documents(self, source_files: List[FileInfo], parse_options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Parse source documents and return file_path -> text."""
        from utils.document_reader import read_document

        parse_options = parse_options or {}
        has_header = parse_options.get("hasHeader", True)
        if isinstance(has_header, str):
            has_header = has_header.strip().lower() not in {"0", "false", "no", "n", "off"}
        parsed_content: Dict[str, str] = {}
        for file_info in source_files:
            if file_info.path in self._file_cache:
                parsed_content[file_info.path] = self._file_cache[file_info.path]
                continue

            content = read_document(
                file_info.path,
                sheet_index=parse_options.get("sheetIndex"),
                has_header=bool(has_header),
            )
            parsed_content[file_info.path] = content
            self._file_cache[file_info.path] = content

        return parsed_content

    def execute_agent(
        self,
        agent_name: str,
        task_spec: TaskSpec,
        **kwargs
    ) -> Any:
        """
        鎵цAgent
        agent_name: agent_a, agent_b, agent_c, agent_d, conversation
        """
        agent = self._get_agent(agent_name)
        if not agent:
            self.logger.error(f"Agent不存在: {agent_name}")
            return None

        try:
            return agent.execute(task_spec, **kwargs)
        except Exception as e:
            self.logger.error(f"Agent执行失败 {agent_name}: {str(e)}")
            return None

    def _normalize_workflow_edges(self, nodes: List[Dict[str, Any]], edges: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
        node_ids = [str(node.get("id") or "") for node in nodes if node.get("id")]
        node_id_set = set(node_ids)
        normalized: List[Dict[str, str]] = []
        seen = set()

        if edges:
            for edge in edges:
                source = str(edge.get("source") or edge.get("from") or "").strip()
                target = str(edge.get("target") or edge.get("to") or "").strip()
                if not source or not target or source == target:
                    continue
                if source not in node_id_set or target not in node_id_set:
                    continue
                key = (source, target)
                if key in seen:
                    continue
                seen.add(key)
                normalized.append({"id": str(edge.get("id") or f"e_{source}_{target}"), "source": source, "target": target})
            return normalized

        for source, target in zip(node_ids, node_ids[1:]):
            normalized.append({"id": f"e_{source}_{target}", "source": source, "target": target})
        return normalized

    def _topological_workflow_nodes(
        self,
        nodes: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]], Dict[str, List[str]], Optional[str]]:
        node_ids = [str(node.get("id") or "") for node in nodes if node.get("id")]
        node_id_set = set(node_ids)
        if len(node_ids) != len(node_id_set):
            return [], {}, {}, "工作流图结构不合法：节点ID重复"

        normalized_edges = self._normalize_workflow_edges(nodes, edges)
        incoming = {node_id: [] for node_id in node_ids}
        outgoing = {node_id: [] for node_id in node_ids}
        indegree = {node_id: 0 for node_id in node_ids}
        for edge in normalized_edges:
            source = edge["source"]
            target = edge["target"]
            outgoing[source].append(target)
            incoming[target].append(source)
            indegree[target] += 1

        order_hint = {node_id: idx for idx, node_id in enumerate(node_ids)}
        by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
        ready = sorted([node_id for node_id, degree in indegree.items() if degree == 0], key=lambda x: order_hint[x])
        ordered_ids: List[str] = []
        while ready:
            current = ready.pop(0)
            ordered_ids.append(current)
            for target in sorted(outgoing[current], key=lambda x: order_hint[x]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
                    ready.sort(key=lambda x: order_hint[x])

        if len(ordered_ids) != len(node_ids):
            return [], incoming, outgoing, "工作流图结构不合法：检测到循环连线"
        return [by_id[node_id] for node_id in ordered_ids], incoming, outgoing, None

    def _merge_node_inputs(self, contents: List[str]) -> str:
        values = [str(content or "").strip() for content in contents if str(content or "").strip()]
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        return "\n\n".join(f"## 上游结果 {idx}\n{value}" for idx, value in enumerate(values, start=1))

    def fill_template(
        self,
        data: Any,
        template: FileInfo,
        output_template: Optional[str] = None,
    ) -> str:
        """
        濉厖妯℃澘
        灏嗘暟鎹～鍏ユ寚瀹氭ā鏉?
        """
        self.logger.info(f"填充模板: {template.name}")
        payload = getattr(data, "data", {}) if data is not None else {}
        if not isinstance(payload, dict):
            return ""
        entities = payload.get("entities")
        if not isinstance(entities, list) or not entities:
            self.logger.warning("跳过模板填充：缺少entities数据")
            return ""

        try:
            from core.agents.agent_d import run_agent_d_fill_from_entities

            fill_result = run_agent_d_fill_from_entities(
                entities=entities,
                template=template.path,
                output_template=output_template or "",
            )
            if not isinstance(fill_result, dict) or not fill_result.get("success"):
                self.logger.warning(f"模板填充失败: {fill_result}")
                return ""
            result_data = fill_result.get("data", {})
            if isinstance(result_data, dict):
                return str(result_data.get("template_output") or "")
            return ""
        except Exception as exc:
            self.logger.error(f"模板填充异常: {exc}")
            return ""

    def execute_workflow_pipeline(self, task_spec: TaskSpec, progress_callback=None) -> Dict[str, Any]:
        """
        缁熶竴宸ヤ綔娴佽妭鐐规祦姘寸嚎鎵ц锛堢敱 coordinator 璋冪敤锛夈€?
        parameters:
            - workflow_nodes: List[dict]
            - output_config: Dict[str, Any]
            - execution_id: str (optional, for blob prefix)
        """
        source = task_spec.source_files[0] if task_spec.source_files else None
        if not source:
            return {"success": False, "message": "缺少源文件"}

        output_config = task_spec.parameters.get("output_config", {}) or {}
        workflow_nodes = task_spec.parameters.get("workflow_nodes", []) or []
        input_config = task_spec.parameters.get("input_config", {}) or {}
        execution_id = str(task_spec.parameters.get("execution_id") or "workflow")

        source_name = Path(source.name or source.path).name
        source_stem = Path(source_name).stem
        save_path = str(output_config.get("savePath") or "").strip()

        configured_format = str(output_config.get("outputFormat") or "").lower()
        if configured_format in ("excel", "xls"):
            configured_format = "xlsx"
        save_suffix_format = Path(save_path).suffix.lower().lstrip(".") if save_path else ""
        if save_suffix_format in ("xls", "excel"):
            save_suffix_format = "xlsx"
        supported_formats = {"md", "txt", "pdf", "xlsx"}
        output_format = configured_format if configured_format in supported_formats else ""
        if output_format not in {"pdf", "xlsx"}:
            if save_suffix_format in {"pdf", "xlsx"}:
                output_format = save_suffix_format
        if not output_format:
            output_format = save_suffix_format if save_suffix_format in supported_formats else "md"

        ext = f".{output_format}"
        out_name = output_filename_from_source(source_name, output_format)
        if save_path:
            resolved_save = Path(save_path)
            if not resolved_save.is_absolute():
                resolved_save = Path(self.config.output_dir) / resolved_save
            if resolved_save.suffix:
                out_path = resolved_save if resolved_save.suffix.lower() == ext else resolved_save.with_suffix(ext)
                out_name = out_path.name
            else:
                out_path = resolved_save / out_name
        else:
            out_path = Path(self.config.output_dir) / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        skip_existing = bool(input_config.get("skipExisting", False))
        if skip_existing and out_path.exists():
            return {
                "success": True,
                "message": "跳过已存在输出(skipExisting=true)",
                "output_file": str(out_path),
                "output": {
                    "name": out_path.name,
                    "path": str(out_path),
                    "blob_name": None,
                    "size": out_path.stat().st_size,
                    "source": source.name,
                },
            }

        parsed = self.parse_documents([source], input_config)
        content = parsed.get(source.path, "")
        if not content:
            return {"success": False, "message": f"无法读取文件内容: {source.name}"}

        workflow_edges = task_spec.parameters.get("workflow_edges", []) or []
        ordered_nodes, incoming, outgoing, graph_error = self._topological_workflow_nodes(workflow_nodes, workflow_edges)
        if graph_error:
            return {"success": False, "message": graph_error}
        total_nodes = max(len(ordered_nodes), 1)
        order_index = {str(node.get("id")): idx for idx, node in enumerate(ordered_nodes, start=1)}
        node_outputs: Dict[str, str] = {}
        output_node_ids: List[str] = []
        result_content = content

        from api.routers.workflows_processors import _process_node

        for original_index, node_dict in enumerate(ordered_nodes, start=1):
            node_id = str(node_dict.get("id", ""))
            node_title = str(node_dict.get("title", "") or node_dict.get("type", ""))
            node_type = str(node_dict.get("type", "")).lower()
            predecessor_ids = incoming.get(node_id, [])
            input_contents = [node_outputs[pred_id] for pred_id in predecessor_ids if pred_id in node_outputs]
            node_input = self._merge_node_inputs(input_contents) if input_contents else result_content

            if node_type == "input":
                node_outputs[node_id] = content
                result_content = content
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"输入节点完成: {node_title}",
                        node_id=node_id,
                        node_title=node_title,
                        node_index=original_index,
                        node_status="completed",
                        node_progress=100,
                    )
                continue

            if node_type == "output":
                output_node_ids.append(node_id)
                node_outputs[node_id] = node_input
                result_content = node_input
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"输出节点就绪: {node_title}",
                        node_id=node_id,
                        node_title=node_title,
                        node_index=original_index,
                        node_status="completed",
                        node_progress=100,
                    )
                continue

            node = SimpleNamespace(
                type=node_dict.get("type", ""),
                title=node_dict.get("title", ""),
                schemaKey=node_dict.get("schemaKey", ""),
                configValues=node_dict.get("configValues", {}) or {},
            )
            if progress_callback:
                progress_callback(
                    original_index,
                    total_nodes,
                    f"处理节点开始: {node.title or node.type}",
                    node_id=node_id,
                    node_title=str(node.title or node.type),
                    node_index=original_index,
                    node_status="running",
                    node_progress=30,
                )
            try:
                node_result = _process_node(node_input, source.name, node, self.config, {})
            except Exception as exc:
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"处理节点失败: {node.title or node.type}({exc})",
                        node_id=node_id,
                        node_title=str(node.title or node.type),
                        node_index=original_index,
                        node_status="failed",
                        node_progress=100,
                    )
                return {"success": False, "message": f"节点处理失败: {node.title or node.type}({exc})"}
            if not node_result:
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"处理节点失败: {node.title or node.type}",
                        node_id=node_id,
                        node_title=str(node.title or node.type),
                        node_index=original_index,
                        node_status="failed",
                        node_progress=100,
                    )
                return {"success": False, "message": f"节点处理结果为空: {node.title or node.type}"}
            node_outputs[node_id] = node_result
            result_content = node_result
            if progress_callback:
                progress_callback(
                    original_index,
                    total_nodes,
                    f"处理节点完成: {node.title or node.type}",
                    node_id=node_id,
                    node_title=str(node.title or node.type),
                    node_index=original_index,
                    node_status="completed",
                    node_progress=100,
                )

        if output_node_ids:
            result_content = self._merge_node_inputs([node_outputs[node_id] for node_id in output_node_ids if node_id in node_outputs])
        else:
            sink_ids = [node_id for node_id in node_outputs if not outgoing.get(node_id)]
            result_content = self._merge_node_inputs([node_outputs[node_id] for node_id in sink_ids]) or result_content

        try:
            if output_format == "pdf":
                from utils.pdf_generator import text_to_pdf
                text_to_pdf(result_content, str(out_path), title=out_name)
                mime_type = "application/pdf"
            elif output_format == "xlsx":
                self._write_xlsx_output(result_content, out_path, str(output_config.get("sheetName") or "Sheet1"))
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                encoding = str(output_config.get("outputEncoding") or "utf-8").lower()
                if encoding not in {"utf-8", "gbk"}:
                    encoding = "utf-8"
                line_ending = "\r\n" if str(output_config.get("lineEnding") or "").lower() == "crlf" else "\n"
                text_output = result_content.replace("\r\n", "\n").replace("\r", "\n")
                if line_ending != "\n":
                    text_output = text_output.replace("\n", line_ending)
                out_path.write_text(text_output, encoding=encoding)
                mime_type = "text/markdown; charset=utf-8" if output_format == "md" else "text/plain; charset=utf-8"
        except Exception as exc:
            for output_node_id in output_node_ids:
                if progress_callback:
                    progress_callback(
                        order_index.get(output_node_id, total_nodes),
                        total_nodes,
                        f"输出节点失败: {output_node_id}({exc})",
                        node_id=output_node_id,
                        node_title=str(next((n.get("title") for n in ordered_nodes if str(n.get("id")) == output_node_id), output_node_id)),
                        node_index=order_index.get(output_node_id, total_nodes),
                        node_status="failed",
                        node_progress=100,
                    )
            return {"success": False, "message": f"输出文件写入失败: {exc}"}
        blob_name = None
        if self.config.storage.enabled and self.config.storage.provider == "azure_blob":
            try:
                blob_name = upload_file_to_storage(
                    out_path,
                    config=self.config,
                    blob_name=build_blob_name(execution_id, out_path.name, prefix=self.config.storage.azure_blob_prefix or "workflows"),
                    content_type=mime_type,
                )
            except Exception as exc:
                self.logger.warning(f"上传工作流产物到Blob失败: {exc}")

        return {
            "success": True,
            "message": "工作流处理完成",
            "output_file": str(out_path),
            "output": {
                "name": out_path.name,
                "path": str(out_path),
                "blob_name": blob_name,
                "size": out_path.stat().st_size,
                "source": source.name,
            },
        }

    def _write_xlsx_output(self, content: str, out_path: Path, sheet_name: str = "Sheet1") -> None:
        """Write text/Markdown/JSON-like content to an xlsx file."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        safe_sheet_name = "".join(ch for ch in (sheet_name or "Sheet1") if ch not in r'[]:*?/\\')[:31] or "Sheet1"
        ws.title = safe_sheet_name

        rows = self._content_to_rows(content)
        if not rows:
            rows = [["内容"], [content]]
        for row in rows:
            ws.append([self._to_excel_cell(cell) for cell in row])

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)

    def _content_to_rows(self, content: str) -> List[List[Any]]:
        text = (content or "").strip()
        if not text:
            return []

        try:
            payload = json.loads(text)
            rows = self._json_to_rows(payload)
            if rows:
                return rows
        except Exception:
            pass

        markdown_rows: List[List[str]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not (line.startswith("|") and line.endswith("|")):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and all(c and set(c) <= {"-", ":"} for c in cells):
                continue
            markdown_rows.append(cells)
        if markdown_rows:
            return markdown_rows

        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",\t;")
            reader = csv.reader(text.splitlines(), dialect)
            rows = [row for row in reader if row]
            if rows and any(len(row) > 1 for row in rows):
                return rows
        except Exception:
            pass

        return [["内容"], *[[line] for line in text.splitlines()]]

    def _json_to_rows(self, payload: Any) -> List[List[Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("entities"), list):
            payload = payload.get("entities")
        if isinstance(payload, dict):
            return [["字段", "值"], *[[key, value] for key, value in payload.items()]]
        if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
            headers: List[str] = []
            for item in payload:
                for key in item.keys():
                    if key not in headers:
                        headers.append(str(key))
            return [headers, *[[item.get(header, "") for header in headers] for item in payload]]
        if isinstance(payload, list):
            return [["值"], *[[item] for item in payload]]
        return []

    @staticmethod
    def _to_excel_cell(value: Any) -> Any:
        """Convert a value to an openpyxl writable cell value."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else value

    def _get_parser(self, file_type: str):
        """Return parser placeholder; parsing is handled by agents."""



        self.logger.warning("Parser is deprecated; use agent-native parsing")
        return None

    def _get_agent(self, agent_name: str):
        """Get agent instance by name."""
        if agent_name in self._agents:
            return self._agents[agent_name]

        agent_map = {
            "agent_a": "core.agents.agent_a.AgentA",
            "agent_b": "core.agents.agent_b.AgentB",
            "agent_c": "core.agents.agent_c.AgentC",
            "agent_d": "core.agents.agent_d.AgentD",
            "conversation": "core.agents.conversation_agent.ConversationAgent",
            "document_understanding": "core.agents.document_understand_agent.DocumentAgent",
        }

        agent_config = agent_map.get(agent_name)
        if not agent_config:
            return None

        try:
            # 分离模块路径和类名
            module_path, class_name = agent_config.rsplit(".", 1)
            if agent_name == "conversation":
                class_name = "ConversationAgent"
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            agent = agent_class(self.config)
            self._agents[agent_name] = agent
            return agent
        except Exception as e:
            self.logger.error(f"加载Agent失败 {agent_name}: {str(e)}")
            return None
