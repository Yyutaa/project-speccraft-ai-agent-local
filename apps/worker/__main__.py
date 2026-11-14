"""Independent local process. Managed roles: clarification, PRD/TD authoring and bounded TD quality."""

import argparse
import json
import os
import signal
import sqlite3
from pathlib import Path
from threading import Event
from uuid import uuid4

from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.managed import execute_model_job
from deliveryflow_speccraft.providers import (
    DeepSeekConfig,
    DeepSeekProvider,
    ProviderConfigurationError,
)
from deliveryflow_speccraft.worker import renew_while_running


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecCraft local background Worker")
    parser.add_argument(
        "--once", action="store_true", help="process at most one queued task"
    )
    parser.add_argument(
        "--database", type=Path, help="server-owned SQLite database path"
    )
    args = parser.parse_args()
    try:
        config = DeepSeekConfig.from_environment(os.environ)
    except ProviderConfigurationError as error:
        parser.exit(2, f"Worker 配置错误：{error}\n")
    root = Path(__file__).resolve().parents[2]
    configured_path = os.environ.get("SPECCRAFT_DB_PATH")
    database = args.database or (
        Path(configured_path)
        if configured_path
        else root / ".deliveryflow-state/runs.sqlite3"
    )
    runner = build_runner(root, database_path=database)
    provider = DeepSeekProvider(config)
    stop = Event()
    owner = f"worker-{os.getpid()}-{uuid4()}"
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.is_set():
            lease = runner._runs.claim_next(owner)
            if lease is not None:
                with renew_while_running(database, lease):
                    result = execute_model_job(
                        runner,
                        provider,
                        owner=owner,
                        claimed=lease,
                    )
                if result is not None:
                    print(
                        json.dumps(
                            {
                                "job_id": result.job_id,
                                "status": result.status,
                                "error_code": result.error_code,
                            }
                        ),
                        flush=True,
                    )
            if args.once:
                break
            if lease is None:
                stop.wait(1.0)
    except (sqlite3.Error, ValueError, RuntimeError, OSError, KeyError):
        parser.exit(1, "Worker 执行失败；未提交计算将按持久任务恢复。\n")
    finally:
        provider.close()
        runner._runs.close()


if __name__ == "__main__":
    main()
