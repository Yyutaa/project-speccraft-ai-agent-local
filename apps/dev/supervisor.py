"""Supervise only processes started by this local launcher; never reclaim ports."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from deliveryflow_speccraft.providers import DeepSeekConfig, ProviderConfigurationError

from apps.api.runtime import RuntimeStatus, WorkerStatus


def select_port(
    value: str | None, default: int, excluded: set[int] | None = None
) -> int:
    try:
        start = int(value) if value is not None else default
    except ValueError:
        raise ValueError("port must be an integer in 1..65535") from None
    if not 1 <= start <= 65535:
        raise ValueError("port must be in 1..65535")
    for port in range(start, min(start + 100, 65536)):
        if port in (excluded or set()):
            continue
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise ValueError("no available local port within 100 candidates")


def worker_configuration(
    environment: Mapping[str, str],
) -> tuple[bool, bool, str | None]:
    mode = environment.get("SPECCRAFT_START_WORKER", "auto")
    if mode not in ("auto", "0", "1"):
        raise ValueError("SPECCRAFT_START_WORKER must be auto, 0 or 1")
    try:
        DeepSeekConfig.from_environment(environment)
    except ProviderConfigurationError as error:
        if mode == "1":
            raise ValueError(str(error)) from None
        return False, False, str(error) if mode == "auto" else "explicitly_disabled"
    return mode != "0", True, None if mode != "0" else "explicitly_disabled"


class Children:
    def __init__(self) -> None:
        self.processes: dict[str, subprocess.Popen[bytes]] = {}

    def start(
        self,
        name: str,
        command: list[str],
        environment: Mapping[str, str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.Popen[bytes]:
        child = subprocess.Popen(
            command, env=environment, cwd=cwd, start_new_session=True
        )
        self.processes[name] = child
        return child

    def failed(self) -> str | None:
        return next(
            (
                name
                for name, child in self.processes.items()
                if child.poll() is not None
            ),
            None,
        )

    def close(self) -> None:
        # Every process group is a new session created by start(), including Vite descendants.
        for child in self.processes.values():
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 7
        for child in self.processes.values():
            try:
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        for child in self.processes.values():
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        self.processes.clear()


def write_status(path: Path, status: RuntimeStatus) -> None:
    status.last_updated = time.time()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(status.model_dump_json())
    temporary.replace(path)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    try:
        enabled, configured, reason = worker_configuration(environment)
        api_port = select_port(environment.get("API_PORT"), 8790)
        web_port = select_port(environment.get("WEB_PORT"), 5190, {api_port})
    except ValueError as error:
        print(f"启动配置错误：{error}", file=sys.stderr)
        return 2
    environment["SPECCRAFT_DB_PATH"] = str(
        Path(
            environment.get(
                "SPECCRAFT_DB_PATH", str(root / ".deliveryflow-state/runs.sqlite3")
            )
        ).resolve()
    )
    environment["VITE_API_TARGET"] = f"http://127.0.0.1:{api_port}"
    children = Children()
    stop = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    with tempfile.TemporaryDirectory(prefix="speccraft-runtime-") as directory:
        path = Path(directory) / "status.json"
        environment["SPECCRAFT_RUNTIME_STATUS_PATH"] = str(path)
        status = RuntimeStatus(
            supervised=True,
            worker=WorkerStatus(
                status="disabled", configured=configured, reason=reason
            ),
        )
        try:
            if enabled:
                worker = children.start(
                    "worker",
                    [sys.executable, "-m", "apps.worker"],
                    environment,
                    cwd=root,
                )
                status.worker = WorkerStatus(
                    status="running", configured=True, reason=None, pid=worker.pid
                )
            write_status(path, status)
            children.start(
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "apps.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                    "--timeout-graceful-shutdown",
                    "5",
                ],
                environment,
                cwd=root,
            )
            children.start(
                "web",
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
                environment,
                cwd=root / "apps/web",
            )
            deadline = time.monotonic() + 40
            ready = False
            while not stop:
                failed = children.failed()
                if failed:
                    if failed == "worker":
                        status.worker.status = "exited"
                        status.worker.reason = "worker_process_exited"
                    write_status(path, status)
                    print(f"{failed} exited; stopping owned services", file=sys.stderr)
                    return 1
                write_status(path, status)
                if not ready:
                    try:
                        for port, endpoint in (
                            (api_port, "/api/health"),
                            (web_port, "/"),
                        ):
                            with urlopen(
                                f"http://127.0.0.1:{port}{endpoint}", timeout=0.5
                            ) as response:
                                if response.status != 200:
                                    raise URLError("not ready")
                        ready = True
                        print(
                            f"Web: http://127.0.0.1:{web_port}\nAPI: http://127.0.0.1:{api_port}/docs\nWorker: {status.worker.status} ({reason or 'configured'})",
                            flush=True,
                        )
                        print(
                            json.dumps(
                                {
                                    name: child.pid
                                    for name, child in children.processes.items()
                                }
                            ),
                            flush=True,
                        )
                    except (OSError, URLError):
                        if time.monotonic() > deadline:
                            print("startup health check timed out", file=sys.stderr)
                            return 1
                time.sleep(0.2 if not ready else 2)
            return 0
        finally:
            children.close()


if __name__ == "__main__":
    raise SystemExit(main())
