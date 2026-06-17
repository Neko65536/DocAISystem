import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))


from core.agents.agent_a import edit_document_with_agent_a


def _load_data_module(data_py: Path):
	spec = importlib.util.spec_from_file_location("test_a_data_module", str(data_py))
	module = importlib.util.module_from_spec(spec)
	assert spec and spec.loader
	spec.loader.exec_module(module)
	return module


def _read_optional_str(module, *names: str, default: str = "") -> str:
	for name in names:
		value = getattr(module, name, None)
		if value is None:
			continue
		text = str(value).strip()
		if text:
			return text
	return default


def _resolve_input_path(value: str, base_dir: Path) -> str:
	path_str = str(value).strip()
	path_str = path_str.replace('\\', '/')
	path = Path(path_str)
	if path.is_absolute():
		return str(path.resolve())
	return str((base_dir / path).resolve())


def main() -> None:
	data_case = sys.argv[1].strip() if len(sys.argv) > 1 else "data2"
	data_py = ROOT / "tests" / "test_a" / data_case / "data.py"
	if not data_py.exists():
		raise SystemExit(f"data case not found: {data_case}")

	module = _load_data_module(data_py)
	instruction = _read_optional_str(module, "instruction", "prompt")
	file_path = _read_optional_str(module, "file_path", "src", "source_file")
	output_file = _read_optional_str(module, "output_file", "output_path", default="")

	if not instruction:
		raise SystemExit(f"missing instruction in {data_py}")
	if not file_path:
		raise SystemExit(f"missing file_path/src/source_file in {data_py}")

	resolved_file_path = _resolve_input_path(file_path, ROOT) if file_path else file_path
	resolved_output_file = _resolve_input_path(output_file, ROOT) if output_file else None

	response = edit_document_with_agent_a(
		instruction=instruction,
		file_path=resolved_file_path,
		output_file=resolved_output_file,
	)

	summary = {
		"success": bool(getattr(response, "success", False)),
		"message": getattr(response, "message", ""),
		"data": getattr(response, "data", None),
		"data_py": str(data_py),
	}
	print(json.dumps(summary, ensure_ascii=False, indent=2))

	if not summary["success"]:
		raise SystemExit(1)


if __name__ == "__main__":
	main()
