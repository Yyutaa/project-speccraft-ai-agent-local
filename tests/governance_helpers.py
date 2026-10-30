"""Explicit v2 test forms; never injected into API clients or production requests."""

from deliveryflow_contracts.facts import SubmitClarificationRequest


def clarification_body(run, command_id: str = "test-command") -> dict:
    if not isinstance(run, dict):
        run = run.model_dump(mode="json")
    batch = run["clarification_batch"]
    return {
        "governance_contract_version": 2,
        "expected_revision": run["ledger"]["revision"],
        "batch_id": batch["batch_id"],
        "batch_revision": batch["revision"],
        "command_id": command_id,
        "actor_claim": "test-user",
        "rationale": "已核对原文与全部产品答案",
        "user_confirmed": True,
        "source_reviews": [
            {
                "review_id": f"review-{index}",
                "candidate_id": item["candidate_id"],
                "candidate_revision": item["candidate_revision"],
                "source_id": item["source_id"],
                "source_sha256": item["source_sha256"],
                "action": "accept",
                "usage": "background_only",
            }
            for index, item in enumerate(run["pending_source_claims"])
        ],
        "answers": [
            {
                "question_id": proposal["question_id"],
                "selected_option_id": proposal["options"][0]["option_id"],
            }
            for proposal in batch["proposals"]
            if proposal["gap_id"] in batch["blocking_gap_ids"]
            and proposal.get("target_kind", "dimension") == "dimension"
        ],
    }


def clarification_request(run, command_id: str = "test-command") -> SubmitClarificationRequest:
    return SubmitClarificationRequest.model_validate(clarification_body(run, command_id))


def admitted_fact(fact_id, dimension, claim):
    """Build legitimate pure-domain fixtures through the public exact-admission boundary."""
    from datetime import UTC, datetime
    from hashlib import sha256

    from deliveryflow_contracts.context import SourceRef, SourceSnapshot
    from deliveryflow_contracts.sources import (
        RunSources,
        SourceAdmissionCommand,
        SourceClaimReview,
    )
    from deliveryflow_speccraft.source_admission import (
        admit_source_claim,
        build_source_candidates,
        make_source_record,
    )

    snapshot = SourceSnapshot(
        source=SourceRef(source_type="inline_requirement"),
        sha256=sha256(claim.encode()).hexdigest(),
        read_status="read",
        content=claim,
    )
    source = make_source_record("fixture-run", snapshot)
    candidate = build_source_candidates(source)[0]
    result = admit_source_claim(
        RunSources(run_id="fixture-run", records=(source,)),
        candidate,
        SourceClaimReview(
            review_id=f"review-{fact_id}",
            candidate_id=candidate.candidate_id,
            candidate_revision=1,
            source_id=source.source_id,
            source_sha256=snapshot.sha256,
            action="accept",
            usage="product" if dimension else "background_only",
            dimension=dimension,
        ),
        SourceAdmissionCommand(
            run_id="fixture-run",
            command_id="fixture-command",
            batch_id="fixture-batch",
            batch_revision=1,
            expected_revision=1,
            actor_claim="fixture-user",
            rationale="fixture explicit admission",
            confirmed_at=datetime.now(UTC),
            user_confirmed=True,
        ),
    )
    assert result.fact is not None
    return result.fact.model_copy(update={"fact_id": fact_id})


def td_review_body(run, command_id='td-review-1', **changes):
    if not isinstance(run, dict):
        run = run.model_dump(mode='json')
    return {
        'governance_contract_version': 2,
        'command_id': command_id,
        'expected_review_revision': run['td_review']['review_revision'],
        'prior_review_id': run['td_review']['current_review_id'],
        'human_conclusion': 'no_conflict_observed',
        'binding': dict(run['td_review']['binding']),
        'actor_claim': 'tech-reviewer',
        'producer_kind': 'human',
        'rationale': '逐项核对冻结 PRD 义务与 TD 正文，未发现未裁决冲突',
        'user_confirmed': True,
        'reviewed_obligation_ids': [item['obligation_id'] for item in run['td_draft']['obligations']],
        'findings': [],
        **changes,
    }


def td_review_request(run, command_id='td-review-1', **changes):
    from deliveryflow_contracts.td import RecordTdReviewRequest
    return RecordTdReviewRequest.model_validate(td_review_body(run, command_id, **changes))
