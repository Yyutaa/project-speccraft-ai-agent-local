"""Downloads are exact published bytes, never drafts or regenerated model content."""

from hashlib import sha256

import pytest
from deliveryflow_contracts.artifacts import ArtifactKind
from deliveryflow_speccraft.artifact_export import published_artifacts
from test_managed_prd_api import client_for
from test_run_sse import completed


@pytest.mark.parametrize(
    "kind,filename",
    [("prd", "PRD.md"), ("td", "TD.md"), ("delivery_spec", "DeliverySpec.json")],
)
def test_exact_utf8_download_matches_approval_and_envelope_hash(
    monkeypatch, kind, filename
):
    runner, run = completed()
    client = client_for(runner, monkeypatch)
    expected = next(
        e.artifact for e in run.artifact_envelopes if e.artifact.kind == kind
    )
    before = runner.get_snapshot(run.run_id)
    response = client.get(
        f"/api/runs/{run.run_id}/artifacts/{kind}",
        params={"revision": expected.revision, "content_hash": expected.content_hash},
    )
    assert response.status_code == 200
    assert (
        response.headers["content-disposition"] == f'attachment; filename="{filename}"'
    )
    assert response.headers["x-content-sha256"] == expected.content_hash
    assert response.headers["etag"] == f'"{expected.content_hash}"'
    assert response.headers["cache-control"] == "no-store"
    assert sha256(response.content).hexdigest() == expected.content_hash
    content = (
        run.prd_draft.content
        if kind == "prd"
        else run.td_draft.content
        if kind == "td"
        else run.delivery_spec.model_dump_json()
    )
    assert response.content == content.encode("utf-8")
    assert runner.get_snapshot(run.run_id) == before


def test_workbench_lists_only_three_current_published_artifacts(monkeypatch):
    runner, run = completed()
    client = client_for(runner, monkeypatch)
    data = client.get(f"/api/runs/{run.run_id}/workbench").json()
    assert [a["filename"] for a in data["artifacts"]] == [
        "PRD.md",
        "TD.md",
        "DeliverySpec.json",
    ]
    assert {a["kind"] for a in data["artifacts"]} == {"prd", "td", "delivery_spec"}
    assert len(published_artifacts(run)) == 3


def test_draft_has_no_downloads_and_cannot_export(tmp_path, monkeypatch):
    from test_managed_human import ready_prd

    runner, run = ready_prd(tmp_path)
    client = client_for(runner, monkeypatch)
    assert client.get(f"/api/runs/{run.run_id}/workbench").json()["artifacts"] == []
    response = client.get(
        f"/api/runs/{run.run_id}/artifacts/prd",
        params={
            "revision": run.prd_draft.revision,
            "content_hash": run.prd_draft.content_hash,
        },
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "artifact_export_unavailable"
    )


@pytest.mark.parametrize(
    "params,code",
    [
        ({"revision": 99, "content_hash": "0" * 64}, "revision_conflict"),
        ({"revision": 1, "content_hash": "0" * 64}, "content_hash_conflict"),
    ],
)
def test_old_download_binding_is_refused_without_side_effects(
    monkeypatch, params, code
):
    runner, run = completed()
    client = client_for(runner, monkeypatch)
    before = runner.get_snapshot(run.run_id)
    response = client.get(f"/api/runs/{run.run_id}/artifacts/prd", params=params)
    assert response.status_code == 409 and response.json()["detail"]["code"] == code
    assert runner.get_snapshot(run.run_id) == before


def test_envelope_bytes_mismatch_is_fail_closed(monkeypatch):
    runner, run = completed()
    envelope = run.artifact_envelopes[0]
    changed = envelope.model_copy(
        update={
            "artifact": envelope.artifact.model_copy(update={"content_hash": "0" * 64})
        }
    )
    corrupted = run.model_copy(
        update={"artifact_envelopes": (changed, *run.artifact_envelopes[1:])}
    )
    runner._runs[run.run_id] = (
        corrupted  # Current Contract permits this historical envelope corruption.
    )
    client = client_for(runner, monkeypatch)
    response = client.get(
        f"/api/runs/{run.run_id}/artifacts/td",
        params={
            "revision": run.td_draft.revision,
            "content_hash": run.td_draft.content_hash,
        },
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "artifact_integrity_conflict"
    )


def test_missing_binding_unknown_kind_and_paths_never_read_disk(monkeypatch):
    runner, run = completed()
    client = client_for(runner, monkeypatch)
    base = f"/api/runs/{run.run_id}/artifacts/"
    assert client.get(base + "prd").status_code == 422
    assert (
        client.get(
            base + "unknown", params={"revision": 1, "content_hash": "0" * 64}
        ).status_code
        == 422
    )
    assert client.get(
        base + "..%2F..%2F.env", params={"revision": 1, "content_hash": "0" * 64}
    ).status_code in (404, 422)
    assert (
        client.get(
            "/api/runs/missing/artifacts/prd",
            params={"revision": 1, "content_hash": "0" * 64},
        ).status_code
        == 404
    )


def test_stale_review_or_audit_never_becomes_export_permission():
    from deliveryflow_speccraft.runner import GovernanceError

    _, run = completed()
    for changes in (
        {"quality_audit_current": False},
        {"td_review": run.td_review.model_copy(update={"status": "stale"})},
    ):
        with pytest.raises(GovernanceError):
            published_artifacts(run.model_copy(update=changes))
    assert published_artifacts(run)[0].metadata.kind is ArtifactKind.PRD
