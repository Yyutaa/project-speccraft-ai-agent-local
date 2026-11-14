import json
import time


def test_runtime_unknown_and_stale(tmp_path, monkeypatch):
    from apps.api.runtime import runtime_status

    monkeypatch.delenv("SPECCRAFT_RUNTIME_STATUS_PATH", raising=False)
    assert runtime_status().worker.status == "unknown"
    path = tmp_path / "runtime.json"
    monkeypatch.setenv("SPECCRAFT_RUNTIME_STATUS_PATH", str(path))
    path.write_text(
        json.dumps(
            {
                "supervised": True,
                "last_updated": time.time(),
                "worker": {
                    "status": "running",
                    "configured": True,
                    "reason": None,
                    "pid": 123,
                },
            }
        )
    )
    assert runtime_status().worker.status == "running"
    data = json.loads(path.read_text())
    data["last_updated"] = time.time() - 20
    path.write_text(json.dumps(data))
    assert runtime_status().worker.status == "stale"
    path.write_text("{bad")
    assert runtime_status().worker.status == "unknown"
