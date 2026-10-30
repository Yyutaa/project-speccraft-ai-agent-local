import pytest
from deliveryflow_contracts.facts import FactLedger
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_speccraft.source_admission import build_source_candidates
from pydantic import ValidationError
from test_source_admission import admit, source
from test_td_runner import runner


def selections():
    return [{"client_ref": f"c-{i}", "start": 0, "end": 3} for i in range(5)]


def test_duplicate_exact_intervals_cannot_be_repackaged_as_five_dimensions():
    from fastapi.testclient import TestClient

    from apps.api import main as api_main

    count = len(api_main.runner._runs)
    response = TestClient(api_main.app).post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "管理员导出报表。",
            "claim_selections": selections(),
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert len(api_main.runner._runs) == count


def test_pure_candidate_builder_rejects_duplicates_but_preserves_distinct_overlapping_ranges():
    record = source()
    with pytest.raises(ValueError):
        build_source_candidates(record, ranges=((3, 8), (3, 8)))
    candidates = build_source_candidates(record, ranges=((3, 8), (3, 9)))
    assert len(candidates) == 2


def test_run_projection_rejects_forged_duplicate_interval_candidates():
    subject = runner()
    run = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="管理员导出")
    )
    candidate = run.pending_source_claims[0]
    payload = run.model_dump()
    payload["pending_source_claims"] = (
        candidate,
        candidate.model_copy(update={"candidate_id": "other"}),
    )
    payload["clarification_batch"]["required_candidate_ids"] = [
        candidate.candidate_id,
        "other",
    ]
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_ledger_rejects_different_candidate_ids_for_identical_source_interval():
    first = admit(source()).fact
    evidence = first.admission_evidence.model_copy(
        update={"candidate_id": "repackaged", "review_id": "other"}
    )
    second = first.model_copy(
        update={"fact_id": "other", "admission_evidence": evidence}
    )
    with pytest.raises(ValidationError):
        FactLedger(revision=2, facts=(first, second))


def test_runner_revalidates_forged_duplicate_selection_without_partial_create():
    subject = runner()
    original = CreateRunRequest(
        governance_contract_version=2, requirement="管理员导出报表。"
    )
    from deliveryflow_contracts.runs import ClaimSelection

    request = original.model_copy(
        update={
            "claim_selections": tuple(ClaimSelection(**item) for item in selections())
        }
    )
    with pytest.raises(ValueError):
        subject.create_run(request)
    assert subject._runs == {} and subject._used_command_ids == {}
