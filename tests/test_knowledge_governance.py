"""S3: references never become facts; governance resolves atomically with five answers."""

from pathlib import Path

import pytest
from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_speccraft.repository_context import (
    HarnessReadError,
    RepositoryHarness,
)
from deliveryflow_speccraft.runner import (
    GovernanceError,
    InMemoryRunner,
    InvalidClarification,
)
from governance_helpers import clarification_body
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def subject(tmp_path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/rules.txt").write_text(
        "仅主管审批。背景参考。", encoding="utf-8"
    )
    for name in ("AGENTS.md", "README.md"):
        (tmp_path / name).write_text("工程约束", encoding="utf-8")
    return InMemoryRunner(
        RepositoryHarness(tmp_path), ROOT / "learning-assets/authoring-pack/v1/prd"
    )


def create(subject, **extra):
    return subject.create_run(
        CreateRunRequest.model_validate(
            {
                "governance_contract_version": 2,
                "requirement": "操作员审批。",
                "context_mode": "guide_only",
                **extra,
            }
        )
    )


def knowledge(**extra):
    return {
        "client_ref": "rule",
        "path": "knowledge/rules.txt",
        "start": 0,
        "end": 6,
        "purpose": "人工审阅参考",
        **extra,
    }


def assumption(**extra):
    return {
        "client_ref": "idea",
        "statement": "假定审批后通知",
        "basis_refs": [{"kind": "candidate", "client_ref": "requirement_candidate"}],
        **extra,
    }


def form(run):
    body = clarification_body(run)
    body["answers"] = [
        item for item in body["answers"] if item["question_id"].startswith("gap-")
    ]
    return body


def resolve_assumption(run, **extra):
    item = run.assumptions[-1]
    return {
        "question_id": f"assumption-{item.assumption_id}",
        "assumption_id": item.assumption_id,
        "expected_assumption_revision": item.revision,
        "action": "reject",
        "rationale": "人工判断不采用",
        **extra,
    }


def submit(subject, run, body):
    return subject.submit_clarification(
        run.run_id, SubmitClarificationRequest.model_validate(body)
    )


def test_knowledge_is_bounded_reference_and_pending_background_is_not_authority(
    subject,
):
    run = create(
        subject,
        knowledge_selections=[
            knowledge(
                related_candidate_refs=["requirement_candidate"],
                related_assumption_refs=["idea"],
            )
        ],
        assumptions=[assumption(risk="low", product_impact="none")],
    )
    assert run.ledger.facts == ()
    assert len(run.knowledge_citations) == 1
    citation = run.knowledge_citations[0]
    assert citation.excerpt == "仅主管审批。"
    assert citation.related_candidate_ids == (
        run.pending_source_claims[0].candidate_id,
    )
    assert citation.related_assumption_ids == (run.assumptions[0].assumption_id,)
    assert run.assumptions[0].producer_kind == "user"
    assert len(run.completeness.gaps) == 5
    after = submit(subject, run, form(run))
    assert after.assumptions[0].status == "pending"
    assert "仅主管审批。" not in {fact.claim for fact in after.ledger.facts}
    assert after.knowledge_citations[0].related_fact_ids == (
        next(f.fact_id for f in after.ledger.facts if f.kind == "fact"),
    )


def test_unknown_assumption_blocks_and_rejection_keeps_evidence_without_fact(subject):
    run = create(subject, assumptions=[assumption()])
    assert run.assumptions[0].risk == "unknown"
    assert any(
        g.target_kind == "assumption" and g.blocking for g in run.completeness.gaps
    )
    with pytest.raises(InvalidClarification):
        submit(subject, run, form(run))
    assert subject.get_run(run.run_id) == run
    body = form(run)
    body["assumption_resolutions"] = [resolve_assumption(run)]
    after = submit(subject, run, body)
    assert after.ledger.revision == 2
    assert after.assumptions[0].status == "rejected"
    assert after.assumption_resolution_evidence[0].actor_claim == "test-user"
    assert len(after.ledger.facts) == 6


def test_product_assumption_accept_requires_explicit_dimension_final_answer(subject):
    run = create(
        subject,
        assumptions=[
            assumption(
                affected_dimensions=["permission"],
                risk="high",
                product_impact="present",
            )
        ],
    )
    body = form(run)
    body["assumption_resolutions"] = [resolve_assumption(run, action="accept")]
    with pytest.raises(GovernanceError, match="assumption_resolution_invalid"):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run
    body["assumption_resolutions"][0]["final_answer_question_ids"] = ["gap-permission"]
    after = submit(subject, run, body)
    assert after.assumptions[0].status == "accepted"
    evidence = after.assumption_resolution_evidence[0]
    assert len(evidence.decision_ids) == 1
    permission = [f for f in after.ledger.facts if f.dimension == "permission"]
    assert len(permission) == 1
    assert permission[0].decision_evidence.resolved_assumption_ids == (
        run.assumptions[0].assumption_id,
    )


def test_revision_preserves_superseded_history_and_resolves_new_version(subject):
    run = create(subject, assumptions=[assumption()])
    body = form(run)
    body["assumption_resolutions"] = [
        resolve_assumption(
            run,
            action="revise",
            revised_assumption={
                "statement": "无产品影响的背景说明",
                "risk": "low",
                "product_impact": "none",
            },
            revised_action="accept",
        )
    ]
    after = submit(subject, run, body)
    assert [a.status for a in after.assumptions] == ["superseded", "accepted"]
    assert [a.revision for a in after.assumptions] == [1, 2]
    assert after.assumptions[1].supersedes_id == run.assumptions[0].assumption_id
    assert after.assumption_resolution_evidence[0].decision_ids == ()


def test_structured_rule_difference_creates_conflict_and_uses_explicit_product_answer(
    subject,
):
    run = create(
        subject,
        claim_selections=[
            {
                "client_ref": "rule-product",
                "start": 0,
                "end": 6,
                "subject_key": "approval",
                "dimension": "permission",
                "rule_excerpt": "操作员审批。",
            }
        ],
        knowledge_selections=[
            knowledge(
                subject_key="approval",
                dimension="permission",
                rule_excerpt="仅主管审批。",
            )
        ],
    )
    assert len(run.context_conflicts) == 1
    conflict = run.context_conflicts[0]
    assert conflict.discoverer_kind == "deterministic_metadata"
    body = form(run)
    body["context_conflict_resolutions"] = [
        {
            "question_id": f"context-conflict-{conflict.conflict_id}",
            "conflict_id": conflict.conflict_id,
            "expected_conflict_revision": 1,
            "action": "answer",
            "rationale": "按人工产品决定",
            "final_answer_question_id": "gap-permission",
        }
    ]
    after = submit(subject, run, body)
    assert after.context_conflicts[0].status == "resolved"
    assert len(after.context_resolution_evidence[0].decision_ids) == 1


def test_untyped_explicit_conflict_can_be_excluded_without_untyped_decision(subject):
    run = create(
        subject,
        knowledge_selections=[knowledge()],
        context_conflicts=[
            {
                "client_ref": "conflict",
                "left_ref": {
                    "kind": "candidate",
                    "client_ref": "requirement_candidate",
                },
                "right_ref": {"kind": "citation", "client_ref": "rule"},
                "reason": "参考材料待确认",
            }
        ],
    )
    conflict = run.context_conflicts[0]
    body = form(run)
    body["context_conflict_resolutions"] = [
        {
            "question_id": f"context-conflict-{conflict.conflict_id}",
            "conflict_id": conflict.conflict_id,
            "expected_conflict_revision": 1,
            "action": "exclude",
            "rationale": "排除业务参考",
            "excluded_reference_id": run.knowledge_citations[0].citation_id,
        }
    ]
    after = submit(subject, run, body)
    assert after.context_resolution_evidence[0].decision_ids == ()
    assert not any(
        f.kind == "decision" and f.dimension is None for f in after.ledger.facts
    )


@pytest.mark.parametrize(
    "fault", ["stale", "missing", "extra", "wrong_question", "wrong_answer"]
)
def test_bad_governance_resolution_is_atomic_and_command_retryable(subject, fault):
    run = create(subject, assumptions=[assumption(affected_dimensions=["acceptance"])])
    body = form(run)
    resolution = resolve_assumption(
        run, action="accept", final_answer_question_ids=["gap-acceptance"]
    )
    body["assumption_resolutions"] = [resolution]
    if fault == "stale":
        resolution["expected_assumption_revision"] = 2
    elif fault == "missing":
        body["assumption_resolutions"] = []
    elif fault == "extra":
        resolution["assumption_id"] = "foreign"
    elif fault == "wrong_question":
        resolution["question_id"] = "gap-role"
    else:
        resolution["final_answer_question_ids"] = ["gap-role"]
    with pytest.raises((GovernanceError, InvalidClarification, ValidationError)):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run
    body = form(run)
    body["assumption_resolutions"] = [resolve_assumption(run)]
    assert submit(subject, run, body).ledger.revision == 2


@pytest.mark.parametrize(
    "extra",
    [
        {
            "assumptions": [
                assumption(basis_refs=[{"kind": "candidate", "client_ref": "missing"}])
            ]
        },
        {"assumptions": [assumption(producer_kind="user")]},
        {
            "assumptions": [
                assumption(basis_refs=[{"kind": "assumption", "client_ref": "idea"}])
            ]
        },
        {"knowledge_selections": [knowledge(start=0, end=7)] * 9},
        {"knowledge_selections": [knowledge(related_candidate_refs=["foreign"])]},
        {
            "knowledge_selections": [knowledge()],
            "claim_selections": [{"client_ref": "rule", "start": 0, "end": 6}],
        },
        {"context_conflicts": [{"client_ref": "bad", "reason": "没有双方引用"}]},
    ],
)
def test_invalid_create_rejects_client_identity_cycles_and_unresolved_references(
    subject, extra
):
    with pytest.raises((ValidationError, GovernanceError)):
        create(subject, **extra)
    assert subject._runs == {}


@pytest.mark.parametrize(
    "path", ["AGENTS.md", "knowledge/../AGENTS.md", "requirements/x.md"]
)
def test_knowledge_cannot_read_other_roles(subject, path):
    with pytest.raises((HarnessReadError, GovernanceError)):
        create(subject, knowledge_selections=[knowledge(path=path)])
    assert subject._runs == {}


def test_equal_content_knowledge_keeps_own_role_and_rejects_guide_identity_substitution(
    subject,
):
    (subject._harness.root / "knowledge/rules.txt").write_text(
        "工程约束", encoding="utf-8"
    )
    run = create(subject, knowledge_selections=[knowledge(end=4)])
    guide = next(
        record
        for record in run.source_records
        if record.source_role == "repository_guide"
    )
    citation = run.knowledge_citations[0]
    assert citation.source_sha256 == guide.snapshot.sha256
    assert citation.source_id != guide.source_id
    payload = run.model_dump()
    payload["knowledge_citations"][0]["source_id"] = guide.source_id
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)
    body = form(run)
    body["source_reviews"][0]["source_id"] = citation.source_id
    with pytest.raises(GovernanceError, match="admission_forbidden_source"):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run
    after = submit(subject, run, form(run))
    assert all(f.source_id != citation.source_id for f in after.ledger.facts)


def test_knowledge_rejects_over_limit_excerpt_without_creating_run(subject):
    (subject._harness.root / "knowledge/rules.txt").write_text(
        "a" * 2049, encoding="utf-8"
    )
    with pytest.raises((GovernanceError, ValidationError)):
        create(subject, knowledge_selections=[knowledge(end=2049)])
    assert subject._runs == {}


def test_knowledge_does_not_expand_guide_only_into_metadata_reading(subject):
    (subject._harness.root / "pyproject.toml").write_bytes(b"\x00private metadata")
    run = create(subject, knowledge_selections=[knowledge()])
    assert len(run.knowledge_citations) == 1
    assert {
        entry.snapshot.normalized_path for entry in run.harness_context.entries
    } == {"AGENTS.md", "README.md"}
    assert not any(
        record.snapshot.normalized_path == "pyproject.toml"
        for record in run.source_records
    )


def test_run_projection_revalidates_citation_hash_and_link_identity(subject):
    run = create(subject, knowledge_selections=[knowledge()])
    for field, value in [
        ("source_sha256", "0" * 64),
        ("related_candidate_ids", ["foreign"]),
    ]:
        payload = run.model_dump()
        payload["knowledge_citations"][0][field] = value
        with pytest.raises(ValidationError):
            RunResponse.model_validate(payload)


def test_two_declared_knowledge_rules_register_structured_difference(subject):
    run = create(
        subject,
        knowledge_selections=[
            knowledge(
                subject_key="approval",
                dimension="permission",
                rule_excerpt="仅主管审批。",
            ),
            knowledge(
                client_ref="rule-two",
                start=6,
                end=11,
                subject_key="approval",
                dimension="permission",
                rule_excerpt="背景参考。",
            ),
        ],
    )
    assert len(run.context_conflicts) == 1
    assert run.context_conflicts[0].dimension == "permission"
    assert run.context_conflicts[0].discoverer_kind == "deterministic_metadata"


def test_run_rejects_orphan_revised_assumption_without_exact_resolution(subject):
    run = create(subject, assumptions=[assumption()])
    body = form(run)
    body["assumption_resolutions"] = [
        resolve_assumption(
            run,
            action="revise",
            revised_assumption={
                "statement": "背景",
                "risk": "low",
                "product_impact": "none",
            },
            revised_action="accept",
        )
    ]
    after = submit(subject, run, body)
    payload = after.model_dump()
    orphan = {**payload["assumptions"][1], "assumption_id": "orphan-child"}
    payload["assumptions"] = (*payload["assumptions"], orphan)
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_pending_candidate_rejects_metadata_rule_outside_its_excerpt(subject):
    run = create(subject)
    payload = run.model_dump()
    payload["pending_source_claims"][0].update(
        subject_key="approval",
        dimension="permission",
        rule_excerpt="不存在于原文的规则",
    )
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_default_source_and_explicit_candidate_aliases_bind_exact_unicode(subject):
    run = create(
        subject,
        requirement="😀操作员。",
        claim_selections=[{"client_ref": "actor", "start": 1, "end": 5}],
        assumptions=[
            assumption(
                basis_refs=[
                    {
                        "kind": "source",
                        "client_ref": "requirement_source",
                        "start": 0,
                        "end": 1,
                    },
                    {"kind": "candidate", "client_ref": "actor"},
                ]
            )
        ],
    )
    assert run.pending_source_claims[0].client_ref == "actor"
    assert [r.excerpt for r in run.assumptions[0].basis_refs] == ["😀", "操作员。"]
    assert all(
        ref.source_id == run.source_records[0].source_id
        for ref in run.assumptions[0].basis_refs
    )


def test_background_acceptance_and_rejected_candidate_keep_only_reference_evidence(
    subject,
):
    run = create(
        subject,
        knowledge_selections=[
            knowledge(related_candidate_refs=["requirement_candidate"])
        ],
        assumptions=[assumption(risk="low", product_impact="none")],
    )
    body = form(run)
    review = body["source_reviews"][0]
    review["action"] = "reject"
    review.pop("usage")
    body["assumption_resolutions"] = [resolve_assumption(run, action="accept")]
    after = submit(subject, run, body)
    assert after.assumptions[0].status == "accepted"
    assert after.assumption_resolution_evidence[0].decision_ids == ()
    assert after.knowledge_citations[0].related_candidate_ids == (
        run.pending_source_claims[0].candidate_id,
    )
    assert after.knowledge_citations[0].related_fact_ids == ()
    assert len(after.ledger.facts) == 5
    assert {f.kind for f in after.ledger.facts} == {"decision"}
    assert not {"仅主管审批。", "假定审批后通知"}.intersection(
        f.claim for f in after.ledger.facts
    )


def test_multiple_assumptions_share_one_explicit_decision_per_dimension(subject):
    run = create(
        subject,
        assumptions=[
            assumption(affected_dimensions=["permission"]),
            assumption(
                client_ref="second", affected_dimensions=["permission", "acceptance"]
            ),
        ],
    )
    body = form(run)
    body["assumption_resolutions"] = [
        {
            "question_id": f"assumption-{a.assumption_id}",
            "assumption_id": a.assumption_id,
            "expected_assumption_revision": 1,
            "action": "accept",
            "rationale": "明确最终产品答案",
            "final_answer_question_ids": [
                f"gap-{d.value}" for d in a.affected_dimensions
            ],
        }
        for a in run.assumptions
    ]
    after = submit(subject, run, body)
    permission = next(f for f in after.ledger.facts if f.dimension == "permission")
    assert set(permission.decision_evidence.resolved_assumption_ids) == {
        a.assumption_id for a in run.assumptions
    }
    assert len([f for f in after.ledger.facts if f.kind == "decision"]) == 5
    assert after.ledger.revision == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "accept"},
        {"action": "revise", "revised_assumption": {"statement": "仍未解决的新假设"}},
        {
            "action": "revise",
            "revised_assumption": {"statement": "仍有产品影响"},
            "revised_action": "accept",
        },
    ],
)
def test_unknown_or_new_unresolved_assumption_cannot_be_accepted(subject, fields):
    run = create(subject, assumptions=[assumption()])
    body = form(run)
    body["assumption_resolutions"] = [resolve_assumption(run, **fields)]
    with pytest.raises((ValidationError, GovernanceError)):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run


@pytest.mark.parametrize("action", ["exclude", "irrelevant"])
def test_dimension_conflict_cannot_be_bypassed_as_background(subject, action):
    run = create(
        subject,
        knowledge_selections=[knowledge()],
        context_conflicts=[
            {
                "client_ref": "conflict",
                "left_ref": {
                    "kind": "candidate",
                    "client_ref": "requirement_candidate",
                },
                "right_ref": {"kind": "citation", "client_ref": "rule"},
                "dimension": "permission",
                "reason": "权限待裁决",
            }
        ],
    )
    conflict = run.context_conflicts[0]
    body = form(run)
    body["context_conflict_resolutions"] = [
        {
            "question_id": f"context-conflict-{conflict.conflict_id}",
            "conflict_id": conflict.conflict_id,
            "expected_conflict_revision": 1,
            "action": action,
            "rationale": "声称仅作背景",
            "excluded_reference_id": run.knowledge_citations[0].citation_id,
        }
    ]
    with pytest.raises(GovernanceError, match="context_conflict_invalid"):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run


def test_unlabeled_knowledge_does_not_claim_automatic_semantic_detection(subject):
    run = create(subject, knowledge_selections=[knowledge()])
    assert run.context_conflicts == ()
    assert {g.dimension for g in run.completeness.gaps} == {
        "role",
        "workflow",
        "permission",
        "failure",
        "acceptance",
    }


@pytest.mark.parametrize("fault", ["symlink", "nontext", "file_limit", "excerpt_utf8"])
def test_knowledge_uses_secure_capture_and_utf8_budgets(subject, fault, tmp_path):
    file = subject._harness.root / "knowledge/rules.txt"
    if fault == "symlink":
        external = tmp_path / "external.txt"
        external.write_text("仅主管审批。", encoding="utf-8")
        file.unlink()
        file.symlink_to(external)
    elif fault == "nontext":
        file.write_bytes(b"\x00not text")
    elif fault == "file_limit":
        file.write_text("a" * 65537, encoding="utf-8")
    elif fault == "excerpt_utf8":
        file.write_text("中" * 683, encoding="utf-8")
    with pytest.raises((HarnessReadError, GovernanceError)):
        create(
            subject,
            knowledge_selections=[knowledge(end=683 if fault == "excerpt_utf8" else 6)],
        )
    assert subject._runs == {}


def test_eight_2kib_citations_are_allowed_and_ninth_is_rejected(subject):
    (subject._harness.root / "knowledge/rules.txt").write_text(
        "a" * 65536, encoding="utf-8"
    )
    selections = [
        knowledge(client_ref=f"k{i}", start=i * 2048, end=(i + 1) * 2048)
        for i in range(8)
    ]
    run = create(subject, knowledge_selections=selections)
    assert len(run.knowledge_citations) == 8
    assert sum(len(c.excerpt.encode()) for c in run.knowledge_citations) == 16384
    with pytest.raises(ValidationError):
        create(
            subject, knowledge_selections=[*selections, knowledge(client_ref="ninth")]
        )


def test_api_roundtrip_reports_stale_conflict_and_preserves_workflow_then_retries(
    subject, monkeypatch
):
    from deliveryflow_speccraft.workflow import RunWorkflow
    from fastapi.testclient import TestClient

    import apps.api.main as api

    monkeypatch.setattr(api, "runner", subject)
    monkeypatch.setattr(api, "workflow", RunWorkflow(subject))
    client = TestClient(api.app)
    response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "操作员审批。",
            "context_mode": "guide_only",
            "knowledge_selections": [knowledge()],
            "assumptions": [assumption()],
            "context_conflicts": [
                {
                    "client_ref": "conflict",
                    "left_ref": {
                        "kind": "candidate",
                        "client_ref": "requirement_candidate",
                    },
                    "right_ref": {"kind": "citation", "client_ref": "rule"},
                    "reason": "参考冲突",
                }
            ],
        },
    )
    assert response.status_code == 201
    before = RunResponse.model_validate(response.json())
    body = form(before)
    conflict = before.context_conflicts[0]
    body["assumption_resolutions"] = [resolve_assumption(before)]
    body["context_conflict_resolutions"] = [
        {
            "question_id": f"context-conflict-{conflict.conflict_id}",
            "conflict_id": conflict.conflict_id,
            "expected_conflict_revision": 2,
            "action": "irrelevant",
            "rationale": "本次范围不适用",
        }
    ]
    path = f"/api/runs/{before.run_id}/clarifications/answers"
    bad = client.post(path, json=body)
    assert bad.status_code == 409
    assert bad.json() == {"detail": {"code": "revision_conflict"}}
    assert client.get(f"/api/runs/{before.run_id}").json() == before.model_dump(
        mode="json"
    )
    assert api.workflow.pending_gate(before.run_id) == "await_clarification"
    body["context_conflict_resolutions"][0]["expected_conflict_revision"] = 1
    good = client.post(path, json=body)
    assert good.status_code == 200
    assert good.json()["ledger"]["revision"] == 2
    assert api.workflow.pending_gate(before.run_id) == "await_prd_review"
    body["command_id"] = "new-upstream-command"
    late = client.post(path, json=body)
    assert late.status_code == 409
    assert late.json() == {"detail": {"code": "invalid_run_transition"}}


def test_author_failure_does_not_commit_governance_objects_or_evidence(
    subject, monkeypatch
):
    run = create(subject, assumptions=[assumption(affected_dimensions=["permission"])])
    body = form(run)
    body["assumption_resolutions"] = [
        resolve_assumption(
            run, action="accept", final_answer_question_ids=["gap-permission"]
        )
    ]
    original = subject._prd_author.author

    def unavailable(*args, **kwargs):
        raise RuntimeError("author unavailable")

    monkeypatch.setattr(subject._prd_author, "author", unavailable)
    with pytest.raises(RuntimeError, match="author unavailable"):
        submit(subject, run, body)
    assert subject.get_run(run.run_id) == run
    monkeypatch.setattr(subject._prd_author, "author", original)
    assert submit(subject, run, body).ledger.revision == 2


def test_anonymous_fixture_is_available_through_default_real_api():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "匿名演示需求",
            "knowledge_selections": [
                {
                    "client_ref": "knowledge-demo",
                    "path": "knowledge/approval-rules.md",
                    "start": 12,
                    "end": 27,
                    "purpose": "人工核对审批规则",
                }
            ],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert (
        payload["knowledge_citations"][0]["excerpt"] == "导出结果需要由审批负责人确认。"
    )
    assert payload["ledger"]["facts"] == []
    assert payload["status"] == "awaiting_clarification"
    assert client.get(f"/api/runs/{payload['run_id']}").json() == payload
