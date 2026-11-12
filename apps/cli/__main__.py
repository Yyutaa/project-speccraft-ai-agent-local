import argparse
import json
import os
from pathlib import Path

from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.runner import RunNotFound


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecCraft project scaffold")
    parser.add_argument("--version", action="store_true", help="show scaffold version")
    parser.add_argument("--run-id", help="read a persistent Run summary without executing it")
    parser.add_argument("--database", type=Path, help="server-owned SQLite database path")
    args = parser.parse_args()
    if args.version:
        print("speccraft-project-scaffold 0.1.0")
        return
    if args.run_id:
        project_root = Path(__file__).resolve().parents[2]
        configured_path = os.environ.get("SPECCRAFT_DB_PATH")
        database = args.database or (Path(configured_path) if configured_path else None)
        runner = build_runner(project_root, database_path=database)
        try:
            run = runner.get_run(args.run_id)
        except RunNotFound:
            parser.exit(2, "Run 不存在。\n")
        print(json.dumps({
            "run_id": run.run_id,
            "status": run.status,
            "available_commands": run.available_commands,
        }, ensure_ascii=False))
        return
    print("SpecCraft 项目脚手架已就绪。")
    print("当前提供基础工程结构，后续能力见 README.md。")


if __name__ == "__main__":
    main()
