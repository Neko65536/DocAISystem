"""Agent_A:文档编辑Agent。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from config import SystemConfig
from core.agents.base_agent import AgentResponse, BaseAgent
from core.llm.llm_service import get_llm_service
from core.orchestrator.task_spec import TaskSpec
from utils.output_naming import output_filename_from_source

from .action_plan import build_action_plan_from_instruction
from .capability_matrix import validate_action_plan_against_files
from .docx_adapter import DocxAdapter
from .md_adapter import MdAdapter
from .txt_adapter import TxtAdapter
from .xlsx_adapter import XlsxAdapter


class AgentA(BaseAgent):
    """负责文档编辑任务的Agent。"""

    def __init__(self, config: Optional[SystemConfig] = None):
        super().__init__(config)
        self.name = "Agent_A"
        self.agent_type = "document_editing"

    def execute(self, task_spec: TaskSpec, **kwargs) -> AgentResponse:
        """执行文档编辑任务。"""
        is_valid, error_msg = self.validate_input(task_spec)
        if not is_valid:
            return AgentResponse(success=False, message=error_msg)

        instruction = task_spec.instruction or ""
        source_paths = [f.path for f in task_spec.source_files]
        action_plan = build_action_plan_from_instruction(instruction)
        plan_dict = action_plan.model_dump()
        plan_actions = plan_dict.get("actions", [])
        precheck = validate_action_plan_against_files(action_plan, task_spec.source_files)

        if not precheck.is_valid:
            first_error = precheck.errors[0] if precheck.errors else {}
            return AgentResponse(
                success=False,
                message=(
                    "执行前校验失败: "
                    f"动作{first_error.get('action_type', 'unknown')}与文件类型"
                    f"{first_error.get('file_type', 'unknown')}不兼容。"
                ),
                data={
                    "status": "precheck_failed",
                    "action_plan": plan_dict,
                    "validation_errors": precheck.errors,
                    "suggestions": [e.get("suggestion") for e in precheck.errors if e.get("suggestion")],
                },
                metadata={
                    "agent": self.name,
                    "stage": "precheck_failed",
                },
            )

        docx_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "docx"), None)
        md_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "md"), None)
        txt_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "txt"), None)
        xlsx_file = next((f for f in task_spec.source_files if f.file_type.value.lower() == "xlsx"), None)

        adapter = None
        source_path: Optional[Path] = None

        if docx_file and Path(docx_file.path).exists():
            source_path = Path(docx_file.path).resolve()
            adapter = DocxAdapter(docx_file.path, llm_service=get_llm_service())
        elif md_file and Path(md_file.path).exists():
            source_path = Path(md_file.path).resolve()
            adapter = MdAdapter(md_file.path)
        elif txt_file and Path(txt_file.path).exists():
            source_path = Path(txt_file.path).resolve()
            adapter = TxtAdapter(txt_file.path)
        elif xlsx_file and Path(xlsx_file.path).exists():
            source_path = Path(xlsx_file.path).resolve()
            adapter = XlsxAdapter(xlsx_file.path)

        if adapter is None or source_path is None:
            return AgentResponse(
                success=False,
                message="未找到可编辑的源文件",
                data={
                    "status": "source_file_missing",
                    "mode": "document_editing",
                    "instruction": instruction,
                    "source_files": source_paths,
                    "action_plan": plan_dict,
                },
                metadata={
                    "agent": self.name,
                    "stage": "source_file_missing",
                },
            )

        def _default_output_path(current_source_path: Path) -> str:
            return str(
                current_source_path.with_name(
                    output_filename_from_source(current_source_path.name, current_source_path.suffix)
                )
            )

        execution_report = []
        extraction_outputs = []
        failed_actions = []
        successful_actions = 0
        output_file = task_spec.output_file

        for action in plan_actions:
            result = adapter.apply_action(action)
            execution_report.append(
                {
                    "action_type": result.action_type,
                    "success": result.success,
                    "message": result.message,
                    "details": result.details,
                }
            )
            if result.success:
                successful_actions += 1
                if result.action_type == "extract_content":
                    extraction_outputs.append(result.details)
            else:
                failed_actions.append(
                    {
                        "action_type": result.action_type,
                        "message": result.message,
                        "details": result.details,
                    }
                )

        real_edit_executed = False
        if successful_actions > 0:
            if not output_file:
                output_file = _default_output_path(source_path)
            output_file = adapter.save(output_file)
            real_edit_executed = True

        base_data = {
            "mode": "document_editing",
            "instruction": instruction,
            "source_files": source_paths,
            "intent": action_plan.intent,
            "action_plan": plan_dict,
            "actions": [a["action_type"] for a in plan_actions],
            "precheck": {
                "passed": True,
                "hints": precheck.hints,
            },
            "edited": real_edit_executed,
            "output_file": output_file,
            "execution_report": execution_report,
            "failed_actions": failed_actions,
            "extraction": extraction_outputs,
        }

        if failed_actions and successful_actions == 0:
            return AgentResponse(
                success=False,
                message=failed_actions[0].get("message") or "文档编辑失败",
                data={
                    **base_data,
                    "status": "failed",
                    "output_file": None,
                    "edited": False,
                },
                metadata={
                    "agent": self.name,
                    "stage": "editing_failed",
                },
            )

        if failed_actions:
            return AgentResponse(
                success=False,
                message=f"部分操作失败：{failed_actions[0].get('message') or '请检查执行报告'}",
                data={
                    **base_data,
                    "status": "partial_failed",
                },
                metadata={
                    "agent": self.name,
                    "stage": "editing_partially_failed",
                },
            )

        if real_edit_executed:
            return AgentResponse(
                success=True,
                message="文档编辑完成",
                data={
                    **base_data,
                    "status": "completed",
                },
                metadata={
                    "agent": self.name,
                    "stage": "docx_executed",
                },
            )

        return AgentResponse(
            success=True,
            message="文档编辑任务已就绪（未进行真实编辑）",
            data={
                **base_data,
                "status": "ready",
            },
            metadata={
                "agent": self.name,
                "stage": "action_plan_defined",
            },
        )

    def validate_input(self, task_spec: TaskSpec) -> tuple[bool, str]:
        """最小输入校验。"""
        if not task_spec.source_files:
            return False, "缺少源文件"
        return True, ""

    def get_capabilities(self) -> Dict[str, Any]:
        """返回Agent能力说明。"""
        return {
            "name": self.name,
            "type": self.agent_type,
            "description": "文档编辑Agent最小骨架（第一步）",
            "supported_formats": ["docx", "md", "xlsx", "txt"],
            "features": [
                "接收文档编辑任务",
                "返回固定结构化结果",
                "为后续动作规划与执行预留接口",
            ],
        }
