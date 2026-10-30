"""Boundary errors from the real workflow preserve state and stable HTTP codes."""

from dataclasses import replace

import pytest
from deliveryflow_speccraft.prd_authoring import FakePrdAuthor
from fastapi.testclient import TestClient
from governance_helpers import clarification_body

from apps.api import main as api_main


@pytest.mark.parametrize(
    "fault,code,status",
    [
        ("input", "model_context_too_large", 413),
        ("output", "model_output_too_large", 413),
        ("shape", "model_output_invalid", 422),
    ],
)
def test_api_maps_real_author_boundary_failures_without_domain_or_graph_commit(
    monkeypatch,
    fault,
    code,
    status,
):
    client = TestClient(api_main.app, raise_server_exceptions=False)
    before = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "需求背景",
        },
    ).json()

    class BadAuthor(FakePrdAuthor):
        def author(self, task):
            output = super().author(task).model_dump(mode="json")
            if fault == "output":
                output["content"] = "x" * (256 * 1024)
            else:
                output["status"] = "completed"
            return output

    if fault == "input":
        monkeypatch.setattr(
            api_main.runner,
            "_prd_pack",
            replace(api_main.runner._prd_pack, guide="x" * (128 * 1024)),
        )
    else:
        monkeypatch.setattr(api_main.runner, "_prd_author", BadAuthor())
    response = client.post(
        f"/api/runs/{before['run_id']}/clarifications/answers",
        json=clarification_body(before),
    )
    assert response.status_code == status
    assert response.json()["detail"] == {"code": code, "committed": False}
    assert client.get(f"/api/runs/{before['run_id']}").json() == before
    assert api_main.workflow.pending_gate(before["run_id"]) == "await_clarification"
