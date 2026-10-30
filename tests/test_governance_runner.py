"""S2 failures protect explicit admission, authority and atomic command boundaries."""

from pathlib import Path

import pytest
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    GovernanceError,
    InMemoryRunner,
    InvalidClarification,
)
from fastapi.testclient import TestClient
from governance_helpers import clarification_body
from pydantic import ValidationError

from apps.api.main import app

ROOT = Path(__file__).resolve().parent.parent


def runner():
    return InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
    )


def create(subject, text="管理员审批。客户审批。"):
    return subject.create_run(
        CreateRunRequest.model_validate(
            {
                "governance_contract_version": 2,
                "requirement": text,
            }
        )
    )


def submit(subject, run, body):
    from deliveryflow_contracts.facts import SubmitClarificationRequest

    return subject.submit_clarification(run.run_id, SubmitClarificationRequest.model_validate(body))


def test_old_create_client_is_rejected_instead_of_implicitly_confirmed():
    response = TestClient(app).post("/api/runs", json={"requirement": "新需求"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "contract_version_required"


def test_creation_has_empty_ledger_and_all_candidates_require_review():
    run = create(runner())
    assert run.ledger.revision == 1
    assert run.ledger.facts == ()
    assert run.prd_draft is None
    assert run.clarification_batch.required_candidate_ids == tuple(
        item.candidate_id for item in run.pending_source_claims
    )
    assert run.pending_source_claims[0].excerpt == "管理员审批。客户审批。"


def test_rejected_source_still_allows_explicit_five_decisions_and_one_revision():
    subject = runner()
    before = create(subject)
    body = clarification_body(before)
    body["source_reviews"][0].update(action="reject")
    body["source_reviews"][0].pop("usage")
    after = submit(subject, before, body)
    assert after.ledger.revision == 2
    assert len(after.ledger.facts) == 5
    assert all(item.kind == "decision" for item in after.ledger.facts)
    assert after.pending_source_claims[0].status == "rejected"
    assert after.source_admission_evidence[0].action == "reject"
    assert all(item.decision_evidence.actor_claim == "test-user" for item in after.ledger.facts)


@pytest.mark.parametrize("fault", ["missing_review", "wrong_batch", "wrong_hash", "missing_answer"])
def test_invalid_complete_form_preserves_whole_run_and_command_can_be_retried(fault):
    subject = runner()
    before = create(subject)
    body = clarification_body(before)
    if fault == "missing_review":
        body["source_reviews"] = []
    elif fault == "wrong_batch":
        body["batch_id"] = "old-batch"
    elif fault == "wrong_hash":
        body["source_reviews"][0]["source_sha256"] = "0" * 64
    else:
        body["answers"] = body["answers"][:-1]
    with pytest.raises((GovernanceError, InvalidClarification)):
        submit(subject, before, body)
    assert subject.get_run(before.run_id) == before
    assert submit(subject, before, clarification_body(before)).status == "prd_awaiting_approval"


def test_background_cannot_answer_dimension_and_never_maps_to_product_scope():
    subject = runner()
    before = create(subject)
    body = clarification_body(before)
    body["answers"][0] = {
        "question_id": body["answers"][0]["question_id"],
        "confirmed_candidate_id": before.pending_source_claims[0].candidate_id,
    }
    with pytest.raises(InvalidClarification):
        submit(subject, before, body)
    assert subject.get_run(before.run_id) == before
    after = submit(subject, before, clarification_body(before))
    background_id = next(item.fact_id for item in after.ledger.facts if item.dimension is None)
    sections = {item.section_id.value: item.fact_ids for item in after.prd_blueprint.sections}
    assert background_id in sections["background"]
    assert background_id not in sections["scope"]
    assert sections["scope"] == sections["journeys"]


def test_v2_projection_rejects_uncaptured_source_registry_snapshot():
    subject = runner()
    before = create(subject)
    payload = before.model_dump()
    record = payload["source_records"][0]
    import hashlib

    record["snapshot"]["content"] = "伪造但内部 Hash 一致的原文"
    record["snapshot"]["sha256"] = hashlib.sha256(
        record["snapshot"]["content"].encode()
    ).hexdigest()
    payload["pending_source_claims"] = ()
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_exact_candidate_reference_adds_fact_without_inventing_a_decision():
    subject = runner()
    before = create(subject, "  操作人员😀。  ")
    body = clarification_body(before)
    body["source_reviews"][0].update(usage="product", dimension="role")
    role_answer = next(item for item in body["answers"] if item["question_id"] == "gap-role")
    role_answer.pop("selected_option_id")
    role_answer["confirmed_candidate_id"] = before.pending_source_claims[0].candidate_id
    after = submit(subject, before, body)
    facts = [item for item in after.ledger.facts if item.kind == "fact"]
    assert len(facts) == 1
    assert facts[0].claim == "操作人员😀。"
    assert facts[0].source.excerpt == "  操作人员😀。  "
    assert not any(
        item.kind == "decision" and item.dimension == "role" for item in after.ledger.facts
    )


def test_conflicting_candidates_need_explicit_decision_and_failed_command_is_retryable():
    subject = runner()
    before = subject.create_run(
        CreateRunRequest.model_validate(
            {
                "governance_contract_version": 2,
                "requirement": "管理员。客户。",
                "claim_selections": [
                    {"client_ref": "a", "start": 0, "end": 4},
                    {"client_ref": "b", "start": 4, "end": 7},
                ],
            }
        )
    )
    body = clarification_body(before)
    for review in body["source_reviews"]:
        review.update(usage="product", dimension="role")
    index = next(i for i, item in enumerate(body["answers"]) if item["question_id"] == "gap-role")
    body["answers"][index] = {
        "question_id": "gap-role",
        "confirmed_candidate_id": before.pending_source_claims[0].candidate_id,
    }
    from deliveryflow_speccraft.runner import GovernanceError

    with pytest.raises(GovernanceError, match="clarification_unresolved"):
        submit(subject, before, body)
    assert subject.get_run(before.run_id) == before
    body["answers"][index] = {
        "question_id": "gap-role",
        "custom_answer": "仅运营员审批",
    }
    after = submit(subject, before, body)
    assert len([item for item in after.ledger.facts if item.dimension == "role"]) == 3
    assert "仅运营员审批" in after.ledger.authoritative_view
    assert "管理员。" not in after.ledger.authoritative_view
    assert "客户。" not in after.ledger.authoritative_view


def test_author_failure_does_not_leave_admission_evidence_or_consume_command(
    monkeypatch,
):
    subject = runner()
    before = create(subject)
    author = subject._prd_author.author

    def unavailable(*args, **kwargs):
        raise RuntimeError("author unavailable")

    monkeypatch.setattr(subject._prd_author, "author", unavailable)
    with pytest.raises(RuntimeError, match="author unavailable"):
        submit(subject, before, clarification_body(before))
    assert subject.get_run(before.run_id) == before
    monkeypatch.setattr(subject._prd_author, "author", author)
    assert submit(subject, before, clarification_body(before)).ledger.revision == 2


def test_accepted_candidate_cannot_lose_its_admitted_fact_in_run_projection():
    from deliveryflow_contracts.facts import FactLedger
    from deliveryflow_speccraft.completeness import CompletenessAnalyzer

    subject = runner()
    before = create(subject)
    after = submit(subject, before, clarification_body(before))
    ledger = FactLedger(revision=2, facts=())
    payload = {
        **before.model_dump(),
        "pending_source_claims": after.pending_source_claims,
        "source_admission_evidence": after.source_admission_evidence,
        "ledger": ledger,
        "completeness": CompletenessAnalyzer().analyze(ledger),
        "clarification_batch": before.clarification_batch.model_copy(
            update={
                "ledger_revision": 2,
                "required_candidate_ids": (),
            }
        ),
    }
    with pytest.raises(ValidationError, match="accepted candidate.*FACT"):
        RunResponse.model_validate(payload)


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/clarifications/answers",
        "/prd/revisions",
        "/approvals/prd",
        "/technical-decisions",
        "/approvals/td",
    ],
)
@pytest.mark.parametrize(
    "body,code",
    [
        ({}, "contract_version_required"),
        ({"governance_contract_version": 2}, "invalid_request"),
        ({"governance_contract_version": "2"}, "invalid_request"),
    ],
)
def test_all_write_endpoints_require_explicit_v2_and_normalize_invalid_contracts(
    suffix, body, code
):
    path = "/api/runs" if not suffix else f"/api/runs/unknown{suffix}"
    response = TestClient(app).post(path, json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": code}}


@pytest.mark.parametrize(
    "field",
    [
        "user_confirmed",
        "actor_claim",
        "rationale",
        "source_reviews",
        "batch_id",
        "batch_revision",
    ],
)
def test_old_clarification_cannot_omit_governance_confirmation(field):
    client = TestClient(app)
    response = client.post(
        "/api/runs", json={"governance_contract_version": 2, "requirement": "需求"}
    )
    before = response.json()
    body = clarification_body(before)
    body.pop(field)
    response = client.post(f"/api/runs/{before['run_id']}/clarifications/answers", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert client.get(f"/api/runs/{before['run_id']}").json() == before


def test_fact_and_ledger_contract_reject_legacy_unconfirmed_source_fact():
    import hashlib

    from deliveryflow_contracts.facts import FactLedger, RequirementFact, SourceEvidence

    payload = {
        "fact_id": "legacy",
        "kind": "fact",
        "dimension": "role",
        "claim": "管理员",
        "source": SourceEvidence(
            sha256=hashlib.sha256("管理员".encode()).hexdigest(), excerpt="管理员"
        ),
    }
    with pytest.raises(ValidationError, match="admission evidence"):
        RequirementFact.model_validate(payload)
    with pytest.raises(ValidationError, match="admission evidence"):
        FactLedger.model_validate({"revision": 1, "facts": (payload,)})


def test_copied_fact_without_admission_cannot_reenter_ledger():
    from deliveryflow_contracts.facts import FactLedger

    subject = runner()
    before = create(subject)
    after = submit(subject, before, clarification_body(before))
    fact = next(item for item in after.ledger.facts if item.kind == "fact")
    forged = fact.model_copy(update={"source_id": None, "admission_evidence": None})
    with pytest.raises(ValidationError, match="admission evidence"):
        FactLedger(revision=2, facts=(forged,))


def test_ledger_itself_rejects_reusing_one_admission_for_two_fact_ids():
    from deliveryflow_contracts.facts import FactLedger

    subject = runner()
    before = create(subject)
    after = submit(subject, before, clarification_body(before))
    fact = next(item for item in after.ledger.facts if item.kind == "fact")
    with pytest.raises(ValidationError, match="candidate version.*one FACT"):
        FactLedger(revision=2, facts=(fact, fact.model_copy(update={"fact_id": "second-fact"})))


def test_identical_hash_harness_snapshot_cannot_replace_product_source_identity(tmp_path):
    for path in ("AGENTS.md", "README.md"):
        (tmp_path / path).write_text("相同原文", encoding="utf-8")
    subject = InMemoryRunner(
        RepositoryHarness(tmp_path), ROOT / "learning-assets/authoring-pack/v1/prd"
    )
    before = subject.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="相同原文",
            context_mode="guide_only",
        )
    )
    guide = before.source_records[1]
    assert guide.snapshot.sha256 == before.source_snapshot.sha256
    payload = before.model_dump()
    payload["pending_source_claims"][0]["source_id"] = guide.source_id
    with pytest.raises(ValidationError, match="product requirement"):
        RunResponse.model_validate(payload)
    body = clarification_body(before)
    body["source_reviews"][0]["source_id"] = guide.source_id
    with pytest.raises(GovernanceError, match="admission_forbidden_source"):
        submit(subject, before, body)
    assert subject.get_run(before.run_id) == before


@pytest.mark.parametrize(
    "fault,status,code",
    [
        ("missing_review", 422, "source_review_required"),
        ("batch_id", 409, "clarification_batch_conflict"),
        ("batch_revision", 409, "clarification_batch_conflict"),
        ("hash", 409, "source_evidence_conflict"),
        ("source", 403, "admission_forbidden_source"),
        ("answer", 422, "invalid_clarification"),
        ("confirmation_false", 422, "invalid_request"),
        ("confirmation_numeric", 422, "invalid_request"),
    ],
)
def test_api_admission_errors_are_stable_and_do_not_commit(fault, status, code):
    client = TestClient(app)
    before = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "需求",
        },
    ).json()
    body = clarification_body(before)
    if fault == "missing_review":
        body["source_reviews"] = []
    elif fault == "batch_id":
        body["batch_id"] = "stale"
    elif fault == "batch_revision":
        body["batch_revision"] = 2
    elif fault == "hash":
        body["source_reviews"][0]["source_sha256"] = "0" * 64
    elif fault == "source":
        body["source_reviews"][0]["source_id"] = before["source_records"][1]["source_id"]
    elif fault == "answer":
        body["answers"] = []
    else:
        body["user_confirmed"] = False if fault == "confirmation_false" else 1
    response = client.post(f"/api/runs/{before['run_id']}/clarifications/answers", json=body)
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert client.get(f"/api/runs/{before['run_id']}").json() == before
    retry = client.post(
        f"/api/runs/{before['run_id']}/clarifications/answers", json=clarification_body(before)
    )
    assert retry.status_code == 200
