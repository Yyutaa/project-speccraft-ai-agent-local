"""HTTP candidate doubles prove the controlled workflow and final download boundary."""

import json
from hashlib import sha256

from deliveryflow_speccraft.composition import build_runner
from test_composition import ROOT
from test_managed_delivery import approval_body, current_review
from test_managed_prd_api import client_for


def test_managed_http_chain_exports_exact_bytes_after_restart_without_more_model_calls(
    tmp_path, monkeypatch
):
    runner, client, run = current_review(tmp_path, monkeypatch)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/approve", json=approval_body(runner, run)
    )
    assert response.status_code == 200
    done = runner.get_run(run.run_id)
    before_calls = runner.get_model_budget(run.run_id).model_calls
    assert before_calls == 7
    metadata = client.get(f"/api/runs/{run.run_id}/workbench").json()["artifacts"]
    downloaded = {}
    for item in metadata:
        response = client.get(
            f"/api/runs/{run.run_id}/artifacts/{item['kind']}",
            params={"revision": item["revision"], "content_hash": item["content_hash"]},
        )
        assert response.status_code == 200
        assert sha256(response.content).hexdigest() == item["content_hash"]
        downloaded[item["filename"]] = response.content
    assert set(downloaded) == {"PRD.md", "TD.md", "DeliverySpec.json"}
    spec = json.loads(downloaded["DeliverySpec.json"])
    assert (
        spec["prd"]["content_hash"]
        == sha256(downloaded["PRD.md"]).hexdigest()
        == done.prd_approval.content_hash
    )
    assert (
        spec["td"]["content_hash"]
        == sha256(downloaded["TD.md"]).hexdigest()
        == done.td_approval.content_hash
    )
    runner._runs.close()
    restored = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    client = client_for(restored, monkeypatch)
    for item in metadata:
        response = client.get(
            f"/api/runs/{run.run_id}/artifacts/{item['kind']}",
            params={"revision": item["revision"], "content_hash": item["content_hash"]},
        )
        assert response.content == downloaded[item["filename"]]
    assert restored.get_model_budget(run.run_id).model_calls == before_calls
    assert restored.get_run(run.run_id) == done
