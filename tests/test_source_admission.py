"""Precise evidence admission; every rejection protects a product authority boundary."""

import hashlib
from datetime import UTC, datetime

import pytest
from deliveryflow_contracts.context import SourceRef, SourceSnapshot, SourceType
from deliveryflow_contracts.facts import FactDimension, FactKind, RequirementFact
from deliveryflow_contracts.sources import (
    ClarificationResolution,
    PendingSourceClaim,
    RunSources,
    SourceAdmissionCommand,
    SourceClaimReview,
    SourceClaimStatus,
    SourceRecord,
)
from deliveryflow_speccraft.source_admission import (
    admit_source_claim,
    build_source_candidates,
    make_source_record,
)
from pydantic import ValidationError

RAW = " \r\n运营员审批😀。\r\n "


def snapshot(content: str = RAW, path: str | None = None) -> SourceSnapshot:
    return SourceSnapshot(
        source=SourceRef(
            source_type=SourceType.REQUIREMENT_FILE if path else SourceType.INLINE_REQUIREMENT,
            path=path,
        ),
        normalized_path=path,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        read_status="read",
        content=content,
    )


def source(path: str | None = None, run_id: str = "run-1") -> SourceRecord:
    return make_source_record(run_id, snapshot(path=path), repository_id="repo-1" if path else None)


def command(**updates: object) -> SourceAdmissionCommand:
    return SourceAdmissionCommand.model_validate(
        {
            "run_id": "run-1",
            "command_id": "command-1",
            "batch_id": "batch-1",
            "batch_revision": 1,
            "expected_revision": 1,
            "actor_claim": "user-1",
            "rationale": "已核对原文并确认用途",
            "confirmed_at": datetime(2026, 10, 29, tzinfo=UTC),
            "user_confirmed": True,
            **updates,
        }
    )


def review(candidate: PendingSourceClaim, **updates: object) -> SourceClaimReview:
    return SourceClaimReview.model_validate(
        {
            "review_id": "review-1",
            "candidate_id": candidate.candidate_id,
            "candidate_revision": candidate.candidate_revision,
            "source_id": candidate.source_id,
            "source_sha256": candidate.source_sha256,
            "action": "accept",
            "usage": "product",
            "dimension": "role",
            **updates,
        }
    )


def admit(
    record: SourceRecord,
    candidate: PendingSourceClaim | None = None,
    **review_updates: object,
):
    claim = candidate or build_source_candidates(record)[0]
    return admit_source_claim(
        RunSources(run_id="run-1", records=(record,)),
        claim,
        review(claim, **review_updates),
        command(),
    )


def test_exact_product_confirmation_preserves_raw_utf8_hash_and_strips_only_claim() -> None:
    record = source()
    candidate = build_source_candidates(record)[0]
    before = (record.model_dump(), candidate.model_dump())
    result = admit(record, candidate)

    assert result.fact is not None
    assert result.fact.kind is FactKind.FACT
    assert result.fact.dimension is FactDimension.ROLE
    assert result.fact.claim == "运营员审批😀。"
    assert result.fact.source_id == record.source_id
    assert result.fact.source.excerpt == RAW
    assert result.fact.source.sha256 == hashlib.sha256(RAW.encode("utf-8")).hexdigest()
    assert result.fact.source.sha256 != hashlib.sha256(result.fact.claim.encode()).hexdigest()
    assert result.evidence.command_id == "command-1"
    assert result.evidence.actor_claim == "user-1"
    assert result.evidence.start == 0
    assert result.evidence.end == len(RAW)
    assert (record.model_dump(), candidate.model_dump()) == before


def test_explicit_intervals_use_unicode_code_points_and_not_utf8_byte_offsets() -> None:
    record = source()
    candidate = build_source_candidates(record, ranges=((3, 10),))[0]
    assert candidate.excerpt == "运营员审批😀。"
    assert admit(record, candidate).fact.claim == "运营员审批😀。"


@pytest.mark.parametrize(
    "path,role",
    [
        ("requirements/request.md", "requirement_file"),
        ("AGENTS.md", "repository_guide"),
        ("README.md", "repository_guide"),
        ("package.json", "repository_metadata"),
        ("knowledge/domain.md", "business_knowledge"),
    ],
)
def test_server_derives_reserved_role_from_path_despite_spoofed_source_type(path, role) -> None:
    record = source(path)
    assert record.source_role == role
    assert record.source_id != record.snapshot.sha256
    if role == "requirement_file":
        assert admit(record).fact is not None
    else:
        with pytest.raises(ValueError, match="product requirement"):
            admit(record)


def test_identical_content_hash_cannot_substitute_harness_identity_or_role() -> None:
    product, guide = source(), source("AGENTS.md")
    assert product.snapshot.sha256 == guide.snapshot.sha256
    candidate = PendingSourceClaim.model_validate(
        {
            **build_source_candidates(product)[0].model_dump(),
            "source_id": guide.source_id,
        }
    )
    registry = RunSources(run_id="run-1", records=(product, guide))
    with pytest.raises(ValueError, match="product requirement"):
        admit_source_claim(registry, candidate, review(candidate), command())
    with pytest.raises(ValidationError, match="role"):
        SourceRecord.model_validate({**guide.model_dump(), "source_role": "requirement_file"})


def test_cross_run_identity_is_rejected_before_admission() -> None:
    with pytest.raises(ValidationError, match="Run"):
        RunSources(run_id="run-1", records=(source(run_id="other-run"),))
    record = source()
    candidate = build_source_candidates(record)[0]
    with pytest.raises(ValueError, match="Run"):
        admit_source_claim(
            RunSources(run_id="run-1", records=(record,)),
            candidate,
            review(candidate),
            command(run_id="other-run"),
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"source_id": "another-source"},
        {"source_sha256": "0" * 64},
        {"start": 1},
        {"end": 999},
        {"excerpt": "改写为管理员使用"},
        {"candidate_revision": 2},
        {"status": SourceClaimStatus.ACCEPTED},
    ],
)
def test_forged_candidate_copy_cannot_bypass_boundary_validation(updates) -> None:
    record = source()
    current = build_source_candidates(record)[0]
    forged = current.model_copy(update=updates)
    with pytest.raises(ValueError):
        admit_source_claim(
            RunSources(run_id="run-1", records=(record,)),
            forged,
            review(current),
            command(),
        )


def test_forged_snapshot_hash_cannot_bypass_boundary_validation() -> None:
    record = source()
    forged = record.model_copy(
        update={"snapshot": record.snapshot.model_copy(update={"sha256": "0" * 64})}
    )
    candidate = build_source_candidates(record)[0]
    registry = RunSources(run_id="run-1", records=(record,)).model_copy(
        update={"records": (forged,)}
    )
    with pytest.raises(ValueError, match="SHA-256"):
        admit_source_claim(registry, candidate, review(candidate), command())


def test_fact_claim_cannot_rewrite_accepted_excerpt_or_reassign_dimension() -> None:
    fact = admit(source()).fact
    for updates in (
        {"claim": "管理员审批"},
        {"dimension": "workflow"},
        {"source_id": "other"},
    ):
        with pytest.raises(ValidationError):
            RequirementFact.model_validate({**fact.model_dump(), **updates})


def test_reject_records_evidence_without_creating_fact() -> None:
    result = admit(source(), action="reject", usage=None, dimension=None)
    assert result.fact is None
    assert result.evidence.action == "reject"
    assert result.evidence.rationale == "已核对原文并确认用途"


def test_background_confirmation_is_explicit_and_does_not_fill_product_dimension() -> None:
    result = admit(source(), usage="background_only", dimension=None)
    assert result.fact is not None
    assert result.fact.dimension is None
    assert result.evidence.usage == "background_only"
    candidate = build_source_candidates(source())[0]
    for updates in (
        {"usage": None},
        {"dimension": None},
        {"usage": "background_only", "dimension": "role"},
    ):
        with pytest.raises(ValidationError):
            review(candidate, **updates)


@pytest.mark.parametrize(
    "updates",
    [
        {"actor_claim": " "},
        {"rationale": "\n "},
        {"user_confirmed": False},
        {"confirmed_at": datetime(2026, 10, 29)},
        {"batch_revision": 0},
    ],
)
def test_confirmation_requires_explicit_traceable_user_command(updates) -> None:
    with pytest.raises(ValidationError):
        command(**updates)


def test_registry_rejects_duplicate_ids_and_paths_and_unapproved_path_roles() -> None:
    record = source("requirements/request.md")
    with pytest.raises(ValidationError):
        RunSources(run_id="run-1", records=(record, record))
    with pytest.raises(ValidationError):
        RunSources(run_id="run-1", records=(record, source("requirements/request.md")))
    with pytest.raises(ValueError):
        source("misc/request.md")


def test_candidate_count_empty_ranges_and_total_utf8_budget_are_enforced() -> None:
    record = make_source_record("run-1", snapshot("中" * 20_000))
    for ranges in (((0, 1),) * 33, ((0, 0),), ((-1, 3),), ((0, 10_001),) * 3):
        with pytest.raises(ValueError):
            build_source_candidates(record, ranges=ranges)
    assert len(build_source_candidates(record)) == 1
    with pytest.raises(ValidationError):
        PendingSourceClaim(
            candidate_id="large",
            source_id=record.source_id,
            source_sha256=record.snapshot.sha256,
            start=0,
            end=30_000,
            excerpt="中" * 30_000,
            candidate_revision=1,
            status="pending",
        )


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"selected_option_id": "a", "custom_answer": "b"},
        {"custom_answer": " "},
        {"confirmed_candidate_id": ""},
    ],
)
def test_clarification_resolution_requires_exactly_one_explicit_choice(updates) -> None:
    with pytest.raises(ValidationError):
        ClarificationResolution(question_id="question-1", **updates)
    assert ClarificationResolution(question_id="question-1", confirmed_candidate_id="candidate-1")


@pytest.mark.parametrize(
    "forgery", ["cross_run", "rewritten_claim", "wrong_source", "missing_candidate"]
)
def test_run_response_rechecks_new_admission_relationships_even_for_model_copies(
    forgery,
) -> None:
    from pathlib import Path

    from deliveryflow_contracts.facts import FactLedger
    from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
    from deliveryflow_speccraft.repository_context import RepositoryHarness
    from deliveryflow_speccraft.runner import InMemoryRunner

    root = Path(__file__).resolve().parent.parent
    runner = InMemoryRunner(
        RepositoryHarness(root / "examples/speccraft/repositories/exportflow-sample"),
        root / "learning-assets/authoring-pack/v1/prd",
    )
    original = runner.create_run(CreateRunRequest(governance_contract_version=2, requirement=RAW))
    record = original.source_records[0]
    candidate = original.pending_source_claims[0]
    result = admit_source_claim(
        RunSources(run_id=original.run_id, records=original.source_records),
        candidate,
        review(candidate, usage="background_only", dimension=None),
        command(run_id=original.run_id),
    )
    payload = {
        **original.model_dump(),
        "pending_source_claims": (result.candidate,),
        "source_admission_evidence": (result.evidence,),
        "ledger": FactLedger(revision=2, facts=(result.fact,)),
    }
    from deliveryflow_speccraft.completeness import CompletenessAnalyzer

    payload["completeness"] = CompletenessAnalyzer().analyze(payload["ledger"])
    payload["clarification_batch"] = original.clarification_batch.model_copy(
        update={
            "ledger_revision": 2,
            "required_candidate_ids": (),
        }
    )
    valid = RunResponse.model_validate(payload)
    assert valid.ledger.facts[0].claim == "运营员审批😀。"
    if forgery == "cross_run":
        payload["source_records"] = (
            record.model_copy(update={"run_id": "other-run"}),
            *original.source_records[1:],
        )
    elif forgery == "missing_candidate":
        payload["pending_source_claims"] = ()
    else:
        fact = result.fact.model_copy(
            update={
                "claim": "管理员审批" if forgery == "rewritten_claim" else result.fact.claim,
                "source_id": "wrong-source" if forgery == "wrong_source" else record.source_id,
            }
        )
        payload["ledger"] = payload["ledger"].model_copy(update={"facts": (fact,)})
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


@pytest.mark.parametrize(
    "dimensions",
    [
        tuple(FactDimension),
        (FactDimension.ROLE, FactDimension.ROLE),
    ],
)
def test_run_response_rejects_multiple_facts_for_one_candidate_version(
    dimensions,
) -> None:
    from pathlib import Path

    from deliveryflow_contracts.facts import FactLedger
    from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
    from deliveryflow_speccraft.repository_context import RepositoryHarness
    from deliveryflow_speccraft.runner import InMemoryRunner

    root = Path(__file__).resolve().parent.parent
    original = InMemoryRunner(
        RepositoryHarness(root / "examples/speccraft/repositories/exportflow-sample"),
        root / "learning-assets/authoring-pack/v1/prd",
    ).create_run(CreateRunRequest(governance_contract_version=2, requirement=RAW))
    candidate = original.pending_source_claims[0]
    registry = RunSources(run_id=original.run_id, records=original.source_records)
    results = tuple(
        admit_source_claim(
            registry,
            candidate,
            review(candidate, dimension=dimension),
            command(run_id=original.run_id, command_id=f"command-{index}"),
        )
        for index, dimension in enumerate(dimensions)
    )
    payload = {
        **original.model_dump(),
        "pending_source_claims": (results[0].candidate,),
        "source_admission_evidence": (results[0].evidence,),
        "ledger": FactLedger(revision=2, facts=()).model_copy(
            update={
                "facts": tuple(result.fact for result in results),
            }
        ),
    }
    with pytest.raises(ValidationError, match="candidate version.*one FACT"):
        RunResponse.model_validate(payload)
