import os
import socket
import sys

import pytest


def test_ports_avoid_foreign_listener_and_validate():
    from apps.dev.supervisor import select_port

    with socket.socket() as foreign:
        foreign.bind(("127.0.0.1", 0))
        foreign.listen()
        port = foreign.getsockname()[1]
        assert select_port(str(port), 5190) != port
        assert foreign.fileno() >= 0
        for invalid in ("0", "-1", "65536", "abc"):
            with pytest.raises(ValueError):
                select_port(invalid, 5190)


def test_owned_process_cleanup_preserves_foreign_process():
    import subprocess

    from apps.dev.supervisor import Children

    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    children = Children()
    try:
        child = children.start(
            "test",
            [sys.executable, "-c", "import time; time.sleep(60)"],
            os.environ.copy(),
        )
        children.close()
        assert child.poll() is not None
        assert foreign.poll() is None
    finally:
        children.close()
        foreign.terminate()
        foreign.wait(timeout=5)


def test_worker_config_does_not_fallback():
    from apps.dev.supervisor import worker_configuration

    assert worker_configuration({})[0] is False
    with pytest.raises(ValueError):
        worker_configuration({"SPECCRAFT_START_WORKER": "1"})
    assert worker_configuration({"SPECCRAFT_START_WORKER": "0"})[0] is False


def test_unexpected_worker_exit_is_detected_and_siblings_cleaned():
    import time

    from apps.dev.supervisor import Children

    children = Children()
    try:
        sibling = children.start(
            "api",
            [sys.executable, "-c", "import time; time.sleep(60)"],
            os.environ.copy(),
        )
        worker = children.start(
            "worker", [sys.executable, "-c", "raise SystemExit(2)"], os.environ.copy()
        )
        worker.wait(timeout=5)
        deadline = time.monotonic() + 2
        while children.failed() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert children.failed() == "worker"
        children.close()
        assert sibling.poll() is not None
    finally:
        children.close()


def test_cleanup_reaches_owned_grandchild(tmp_path):
    import time

    from apps.dev.supervisor import Children

    # A grandchild holds a real listening socket; cleanup must release it too.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    ready = tmp_path / "ready"
    grandchild = f"import socket,time; from pathlib import Path; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); Path({str(ready)!r}).touch(); time.sleep(60)"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{grandchild!r}]); time.sleep(60)"
    children = Children()
    try:
        children.start("web", [sys.executable, "-c", parent], os.environ.copy())
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        children.close()
        with socket.socket() as released:
            released.bind(("127.0.0.1", port))
    finally:
        children.close()
