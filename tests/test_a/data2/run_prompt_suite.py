from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
TEST_DATA_DIR = ROOT / "tests" / "test_a" / "data"
DATA2_DIR = ROOT / "tests" / "test_a" / "data2"
OUTPUT_DIR = DATA2_DIR / "suite_outputs"
REPORT_JSON = DATA2_DIR / "coverage_report.json"
REPORT_MD = DATA2_DIR / "coverage_report.md"
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_OUTPUT_DIR = OUTPUT_DIR / RUN_ID

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.agents.agent_a import edit_document_with_agent_a  # noqa: E402

# 直接复用 data.py 的 prompt_suite 和动作全集，避免维护两份清单。
import data as suite_data  # noqa: E402


def _find_source_file(file_type: str) -> Path:
    ext_map = {
        "docx": ".docx",
        "md": ".md",
        "txt": ".txt",
        "xlsx": ".xlsx",
    }
    ext = ext_map[file_type]
    candidates = sorted(TEST_DATA_DIR.glob(f"*{ext}"))
    if not candidates:
        raise FileNotFoundError(f"未找到 {file_type} 样本文件（目录: {TEST_DATA_DIR}）")
    return candidates[0]


def _safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s)


def _normalize_action_name(name: str) -> str:
    raw = str(name).strip()
    if not raw:
        return ""

    if raw.startswith("ActionType."):
        raw = raw.split(".", 1)[1]

    raw = raw.strip().lower()
    return raw


def _extract_actions(resp: Any) -> List[str]:
    data = getattr(resp, "data", None)
    if isinstance(data, dict):
        action_plan = data.get("action_plan")
        if isinstance(action_plan, dict):
            actions = action_plan.get("actions", [])
            if isinstance(actions, list):
                out = []
                for action in actions:
                    if isinstance(action, dict):
                        action_type = _normalize_action_name(str(action.get("action_type", "")))
                        if action_type:
                            out.append(action_type)
                if out:
                    return out
        actions_fallback = data.get("actions", [])
        if isinstance(actions_fallback, list):
            normalized = [_normalize_action_name(str(a)) for a in actions_fallback]
            return [a for a in normalized if a]
    return []


def _run_one(file_type: str, prompt_index: int, prompt_text: str, source_path: Path) -> Dict[str, Any]:
    out_dir = RUN_OUTPUT_DIR / file_type
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"prompt_{prompt_index + 1:02d}{source_path.suffix}"

    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        response = edit_document_with_agent_a(
            instruction=prompt_text,
            file_path=str(source_path),
            output_file=str(output_file),
        )
        success = bool(getattr(response, "success", False))
        message = str(getattr(response, "message", ""))
        data = getattr(response, "data", None)
        actions = _extract_actions(response)

        return {
            "file_type": file_type,
            "prompt_index": prompt_index + 1,
            "prompt": prompt_text,
            "source_file": str(source_path),
            "output_file": str(output_file),
            "success": success,
            "message": message,
            "detected_actions": actions,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "response_data": data,
        }
    except Exception as exc:
        return {
            "file_type": file_type,
            "prompt_index": prompt_index + 1,
            "prompt": prompt_text,
            "source_file": str(source_path),
            "output_file": str(output_file),
            "success": False,
            "message": f"异常: {exc}",
            "detected_actions": [],
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "response_data": None,
        }


def _build_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    supported_actions = list(getattr(suite_data, "all_supported_actions", []))
    covered_actions = sorted(
        {
            action
            for item in results
            for action in item.get("detected_actions", [])
            if action
        }
    )
    uncovered_actions = sorted(set(supported_actions) - set(covered_actions))

    total = len(results)
    success = sum(1 for item in results if item.get("success"))
    failed = total - success

    by_type: Dict[str, Dict[str, Any]] = {}
    for item in results:
        ft = str(item.get("file_type", "unknown"))
        info = by_type.setdefault(ft, {"total": 0, "success": 0, "failed": 0})
        info["total"] += 1
        if item.get("success"):
            info["success"] += 1
        else:
            info["failed"] += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": RUN_ID,
        "workspace": str(ROOT),
        "suite_file": str(DATA2_DIR / "data.py"),
        "run_output_dir": str(RUN_OUTPUT_DIR),
        "total_prompts": total,
        "success_count": success,
        "failed_count": failed,
        "supported_actions_total": len(supported_actions),
        "covered_actions_count": len(covered_actions),
        "coverage_ratio": round((len(covered_actions) / len(supported_actions)) * 100, 2)
        if supported_actions
        else 0.0,
        "supported_actions": supported_actions,
        "covered_actions": covered_actions,
        "uncovered_actions": uncovered_actions,
        "summary_by_file_type": by_type,
        "results": results,
    }


def _write_markdown_report(report: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# AgentA Prompt Suite 覆盖报告")
    lines.append("")
    lines.append(f"- 生成时间: {report.get('generated_at', '')}")
    lines.append(f"- prompt 总数: {report.get('total_prompts', 0)}")
    lines.append(f"- 成功数: {report.get('success_count', 0)}")
    lines.append(f"- 失败数: {report.get('failed_count', 0)}")
    lines.append(
        f"- 动作覆盖: {report.get('covered_actions_count', 0)}/{report.get('supported_actions_total', 0)} "
        f"({report.get('coverage_ratio', 0)}%)"
    )
    lines.append("")

    lines.append("## 分类型统计")
    by_type = report.get("summary_by_file_type", {})
    for ft in sorted(by_type.keys()):
        info = by_type[ft]
        lines.append(
            f"- {ft}: total={info.get('total', 0)}, success={info.get('success', 0)}, failed={info.get('failed', 0)}"
        )
    lines.append("")

    lines.append("## 未覆盖动作")
    uncovered = report.get("uncovered_actions", [])
    if uncovered:
        for action in uncovered:
            lines.append(f"- {action}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 逐条执行结果")
    for item in report.get("results", []):
        status = "OK" if item.get("success") else "ERR"
        actions = ", ".join(item.get("detected_actions", [])) or "(无)"
        lines.append(
            f"- [{status}] {item.get('file_type')}/prompt_{item.get('prompt_index'):02d} "
            f"actions=[{actions}] message={item.get('message', '')}"
        )

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    prompt_suite = getattr(suite_data, "prompt_suite", None)
    if not isinstance(prompt_suite, dict) or not prompt_suite:
        raise SystemExit("data.py 中未找到有效的 prompt_suite")

    results: List[Dict[str, Any]] = []

    for file_type, prompts in prompt_suite.items():
        if not isinstance(prompts, list):
            continue

        try:
            source_file = _find_source_file(file_type)
        except Exception as exc:
            for i, prompt_text in enumerate(prompts):
                results.append(
                    {
                        "file_type": file_type,
                        "prompt_index": i + 1,
                        "prompt": str(prompt_text),
                        "source_file": "",
                        "output_file": "",
                        "success": False,
                        "message": f"缺少样本文件: {exc}",
                        "detected_actions": [],
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                        "response_data": None,
                    }
                )
            continue

        for i, prompt_text in enumerate(prompts):
            results.append(_run_one(file_type, i, str(prompt_text), source_file))

    report = _build_report(results)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_report(report)

    print(json.dumps({
        "total_prompts": report["total_prompts"],
        "success_count": report["success_count"],
        "failed_count": report["failed_count"],
        "covered_actions_count": report["covered_actions_count"],
        "supported_actions_total": report["supported_actions_total"],
        "coverage_ratio": report["coverage_ratio"],
        "report_json": str(REPORT_JSON),
        "report_md": str(REPORT_MD),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
