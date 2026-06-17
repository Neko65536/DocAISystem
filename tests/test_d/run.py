import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
	sys.path.insert(0, str(SRC))


from core.agents.agent_d import run_agent_d_from_data_file


def main() -> None:
	data_case = sys.argv[1].strip() if len(sys.argv) > 1 else "data7"
	data_py = ROOT / "tests" / "test_d" / data_case / "data.py"
	if not data_py.exists():
		raise SystemExit(f"data case not found: {data_case}")

	summary = run_agent_d_from_data_file(data_py)
	summary["data_py"] = str(data_py)
	print(json.dumps(summary, ensure_ascii=False, indent=2))

	if not bool(summary.get("success")):
		raise SystemExit(1)


if __name__ == "__main__":
	main()
