"""Intent routing for chat requests with attached documents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents.agent_a.instruction_parser import parse_instruction_rule_first
from core.llm import get_llm_service


CHAT_MODE = "default_conversation"
DOCUMENT_UNDERSTANDING_MODE = "document_understanding"
DOCUMENT_EDITING_MODE = "document_editing"
ENTITY_EXTRACTION_MODE = "entity_extraction"
TABLE_FILLING_MODE = "table_filling"

EDITABLE_FILE_EXTENSIONS = {"doc", "docx", "md", "txt", "xls", "xlsx"}
DOCUMENT_FILE_EXTENSIONS = EDITABLE_FILE_EXTENSIONS | {"pdf"}

DOCUMENT_EDIT_ACTIONS = {
    "bold_heading",
    "insert_page_number",
    "unify_style",
    "reorder_paragraphs",
    "batch_format",
    "replace_text",
    "insert_toc",
    "auto_column_width",
    "freeze_header_row",
    "remove_blank_lines",
    "set_font_family",
    "set_font_color",
    "set_font_size",
    "set_paragraph_alignment",
    "set_line_spacing",
    "set_first_line_indent",
    "set_highlight",
    "insert_table",
    "insert_footer_text",
    "insert_generated_content",
    "set_heading_numbering",
    "set_italic",
    "set_underline",
    "set_paragraph_spacing",
    "set_bullet_list",
    "set_numbered_list",
    "set_paragraph_shading",
    "set_paragraph_border",
    "add_hyperlink",
}

ROUTABLE_MODES = {
    CHAT_MODE,
    DOCUMENT_UNDERSTANDING_MODE,
    DOCUMENT_EDITING_MODE,
    ENTITY_EXTRACTION_MODE,
    TABLE_FILLING_MODE,
}


class _UnavailableLLM:
    def is_available(self) -> bool:
        return False


@dataclass
class IntentRouteResult:
    mode: str
    confidence: float = 0.0
    source: str = "fallback"
    reason: str = ""


class IntentRouter:
    """Classify a default chat request before dispatching to a task flow."""

    def resolve(
        self,
        current_mode: str,
        content: str,
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> IntentRouteResult:
        mode = (current_mode or CHAT_MODE).strip() or CHAT_MODE
        if mode != CHAT_MODE:
            return IntentRouteResult(mode=mode, confidence=1.0, source="explicit")

        selected_files = [f for f in (files or []) if f.get("is_selected", True) is not False]
        selected_templates = [f for f in (template_files or []) if f.get("is_selected", True) is not False]
        if not str(content or "").strip() or not selected_files:
            return IntentRouteResult(mode=CHAT_MODE, confidence=1.0, source="no_attachment")

        llm_result = self._resolve_with_llm(content, selected_files, selected_templates)
        if llm_result and self._is_usable_llm_result(llm_result, selected_files, selected_templates):
            return llm_result

        return self._resolve_with_local_capability(content, selected_files, selected_templates)

    def _resolve_with_llm(
        self,
        content: str,
        files: List[Dict[str, Any]],
        template_files: List[Dict[str, Any]],
    ) -> Optional[IntentRouteResult]:
        llm = get_llm_service()
        if not llm or not hasattr(llm, "is_available") or not llm.is_available():
            return None

        file_summary = self._summarize_files(files)
        template_summary = self._summarize_files(template_files)
        system_prompt = (
            "你是文档智能系统的意图路由器，只负责判断用户当前请求应进入哪个功能模块。"
            "不要执行任务，不要解释过程，只输出JSON。"
            "可选mode只有default_conversation、document_understanding、document_editing、entity_extraction、table_filling。"
            "判断原则："
            "1. 用户要求修改、整理后写回、添加到、生成输出文件、调整格式、替换、排版时，选document_editing。"
            "2. 用户只询问、总结、解释、问答文档内容但不要求生成新文件时，选document_understanding。"
            "3. 用户要求把非结构化内容抽成字段/实体/JSON/表时，选entity_extraction。"
            "4. 用户要求用数据填入模板或生成填表结果且有模板文件时，选table_filling。"
            "5. 与文件无关的普通聊天选default_conversation。"
            "输出格式：{\"mode\":\"...\",\"confidence\":0到1,\"reason\":\"一句话原因\"}"
        )
        user_prompt = (
            f"用户请求：{content}\n"
            f"当前数据文件：{file_summary or '无'}\n"
            f"当前模板文件：{template_summary or '无'}\n"
            "请输出严格JSON。"
        )
        try:
            raw = llm.chat_with_system(system_prompt, user_prompt, temperature=0.0, max_tokens=300)
        except Exception:
            return None

        payload = self._load_json_object(raw)
        if not payload:
            return None
        mode = str(payload.get("mode") or "").strip()
        if mode not in ROUTABLE_MODES:
            return None
        try:
            confidence = float(payload.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        return IntentRouteResult(
            mode=mode,
            confidence=max(0.0, min(1.0, confidence)),
            source="llm",
            reason=str(payload.get("reason") or "").strip(),
        )

    def _is_usable_llm_result(
        self,
        result: IntentRouteResult,
        files: List[Dict[str, Any]],
        template_files: List[Dict[str, Any]],
    ) -> bool:
        if result.mode == DOCUMENT_EDITING_MODE:
            return result.confidence >= 0.55 and self._has_file_with_extension(files, EDITABLE_FILE_EXTENSIONS)
        if result.mode == TABLE_FILLING_MODE:
            return result.confidence >= 0.55 and bool(files) and bool(template_files)
        if result.mode in {DOCUMENT_UNDERSTANDING_MODE, ENTITY_EXTRACTION_MODE}:
            return result.confidence >= 0.55 and self._has_file_with_extension(files, DOCUMENT_FILE_EXTENSIONS)
        return result.confidence >= 0.75

    def _resolve_with_local_capability(
        self,
        content: str,
        files: List[Dict[str, Any]],
        template_files: List[Dict[str, Any]],
    ) -> IntentRouteResult:
        if self._has_file_with_extension(files, EDITABLE_FILE_EXTENSIONS):
            try:
                parsed = parse_instruction_rule_first(content, llm_service=_UnavailableLLM())
            except Exception:
                parsed = {}
            actions = parsed.get("actions") if isinstance(parsed, dict) else []
            for action in actions if isinstance(actions, list) else []:
                action_type = str((action or {}).get("action_type") or "").strip()
                if action_type in DOCUMENT_EDIT_ACTIONS:
                    return IntentRouteResult(
                        mode=DOCUMENT_EDITING_MODE,
                        confidence=0.7,
                        source="local_action_plan",
                        reason="本地动作规划识别为文档编辑操作",
                    )

        if template_files and files:
            return IntentRouteResult(
                mode=TABLE_FILLING_MODE,
                confidence=0.6,
                source="file_capability",
                reason="同时选择了数据文件和模板文件",
            )

        return IntentRouteResult(mode=CHAT_MODE, confidence=0.5, source="fallback")

    def _has_file_with_extension(self, files: List[Dict[str, Any]], extensions: set[str]) -> bool:
        for item in files or []:
            suffix = Path(self._file_name(item)).suffix.lower().lstrip(".")
            if suffix in extensions:
                return True
        return False

    def _file_name(self, item: Dict[str, Any]) -> str:
        return str(
            item.get("file_name")
            or item.get("name")
            or item.get("storage_key")
            or item.get("file_path")
            or item.get("path")
            or ""
        ).strip()

    def _summarize_files(self, files: List[Dict[str, Any]]) -> str:
        parts = []
        for item in files or []:
            name = self._file_name(item)
            if not name:
                continue
            suffix = Path(name).suffix.lower() or "unknown"
            parts.append(f"{Path(name).name}({suffix})")
        return "、".join(parts[:12])

    def _load_json_object(self, raw: str) -> Optional[Dict[str, Any]]:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
