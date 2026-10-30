import pytest
from deliveryflow_contracts.td import TdApprovalRequest
from deliveryflow_speccraft.runner import GovernanceError
from governance_helpers import td_review_request
from test_td_runner import approve_prd, prd_ready, runner


def awaiting_td(subject):
    return approve_prd(subject, prd_ready(subject))


def approval(run, **changes):
    return TdApprovalRequest.model_validate(
        {
            "governance_contract_version": 2,
            "revision": run.td_draft.revision,
            "content_hash": run.td_draft.content_hash,
            "actor": "tech-owner",
            "rationale": "审阅后批准",
            "review_id": run.td_review.current_review_id or "missing-review",
            "expected_review_revision": run.td_review.review_revision,
            **changes,
        }
    )


def finding(run):
    prd = run.prd_draft.content
    td = run.td_draft.content
    obligation = run.td_draft.obligations[0]
    return {
        "finding_id": "permission-conflict",
        "producer_kind": "human",
        "category": "product_conflict",
        "obligation_ids": [obligation.obligation_id],
        "prd_excerpt": {"start": 0, "end": 10, "excerpt": prd[:10]},
        "td_excerpt": {"start": 0, "end": 10, "excerpt": td[:10]},
        "reason": "正文放宽冻结权限",
        "disposition": "confirmed_conflict",
    }


def test_missing_review_has_server_binding_and_blocks_approval():
    subject = runner()
    run = awaiting_td(subject)
    assert run.td_review.status == "missing"
    assert run.td_review.review_revision == 0
    assert run.td_review.binding.td_content_hash == run.td_draft.content_hash
    assert [cmd.value for cmd in run.available_commands] == ["record_td_review", "revise_td"]
    with pytest.raises(GovernanceError) as failure:
        subject.approve_td(run.run_id, approval(run))
    assert failure.value.code == "td_review_required"
    assert subject.get_run(run.run_id) == run


def test_explicit_complete_human_review_enables_bound_approval():
    subject = runner()
    run = awaiting_td(subject)
    reviewed = subject.record_td_review(run.run_id, td_review_request(run))
    assert reviewed.td_review.status == "ready"
    assert reviewed.td_review.review_revision == 1
    assert len(reviewed.td_review_records) == 1
    done = subject.approve_td(run.run_id, approval(reviewed))
    assert done.td_approval.review_id == reviewed.td_review.current_review_id
    assert done.td_approval.expected_review_revision == 1


def test_valid_conflict_is_successfully_saved_and_cannot_be_erased_by_empty_review():
    subject = runner()
    run = awaiting_td(subject)
    request = td_review_request(
        run, findings=[finding(run)], human_conclusion="changes_required"
    )
    blocked = subject.record_td_review(run.run_id, request)
    assert blocked.td_review.status == "blocked"
    assert blocked.td_review.blocking_finding_ids == ("permission-conflict",)
    with pytest.raises(GovernanceError) as failure:
        subject.record_td_review(run.run_id, td_review_request(blocked, "retry"))
    assert failure.value.code == "invalid_td_review"
    assert subject.get_run(run.run_id) == blocked
    dismissed = {
        "finding_id": "permission-conflict",
        "disposition": "dismissed",
        "disposition_rationale": "人工核对：摘录不构成权限放宽",
    }
    reviewed = subject.record_td_review(
        run.run_id,
        td_review_request(blocked, "retry", existing_finding_dispositions=[dismissed]),
    )
    assert reviewed.td_review.status == "ready"
    assert (
        reviewed.td_review_records[-1].prior_review_id
        == blocked.td_review.current_review_id
    )
    assert len(reviewed.td_review_records) == 2


@pytest.mark.parametrize(
    "change,code",
    [
        ({"binding": {"td_content_hash": "0" * 64}}, "td_review_conflict"),
        ({"binding": {"obligations_hash": "0" * 64}}, "td_review_conflict"),
        ({"expected_review_revision": 9}, "td_review_conflict"),
        ({"reviewed_obligation_ids": ["unknown"]}, "invalid_td_review"),
        ({"findings": "forged"}, "invalid_td_review"),
    ],
)
def test_review_rejection_is_atomic_and_does_not_consume_command_id(change, code):
    subject = runner()
    run = awaiting_td(subject)
    if change.get("findings") == "forged":
        item = finding(run)
        item["td_excerpt"]["excerpt"] = "x" * 10
        change = {"findings": [item]}
    request = td_review_request(run)
    payload = request.model_dump(mode="json")
    if "binding" in change:
        change = {"binding": payload["binding"] | change["binding"]}
    payload.update(change)
    with pytest.raises(GovernanceError) as failure:
        subject.record_td_review(run.run_id, type(request).model_validate(payload))
    assert failure.value.code == code
    assert subject.get_run(run.run_id) == run
    assert subject.record_td_review(run.run_id, request).td_review.status == "ready"


def test_same_td_review_invalidates_previous_approval_and_deduplicates_success():
    subject = runner()
    run = awaiting_td(subject)
    first = subject.record_td_review(run.run_id, td_review_request(run))
    old_approval = approval(first)
    second = subject.record_td_review(run.run_id, td_review_request(first, "review-2"))
    assert second.td_review.current_review_id != first.td_review.current_review_id
    with pytest.raises(GovernanceError, match="td_review_conflict"):
        subject.approve_td(run.run_id, old_approval)
    from deliveryflow_speccraft.runner import DuplicateCommand

    with pytest.raises(DuplicateCommand):
        subject.record_td_review(run.run_id, td_review_request(second))
    assert subject.get_run(run.run_id) == second


def test_revalidated_model_producer_cannot_submit_a_human_record():
    subject = runner()
    run = awaiting_td(subject)
    request = td_review_request(run).model_copy(update={"producer_kind": "model"})
    with pytest.raises(GovernanceError, match="invalid_td_review"):
        subject.record_td_review(run.run_id, request)
    assert subject.get_run(run.run_id) == run


def test_permission_relaxation_in_prose_passes_structure_but_human_finding_blocks():
    from deliveryflow_speccraft.td import (
        extract_prd_obligations,
        validate_td_obligations,
    )
    from deliveryflow_speccraft.td_authoring import FakeTdAuthor

    class PermissionRelaxingAuthor(FakeTdAuthor):
        def author(self, task):
            result = super().author(task)
            return result.model_copy(
                update={
                    "content": result.content
                    + "\n所有普通用户均可导出，无需管理员权限。\n",
                }
            )

    subject = runner(PermissionRelaxingAuthor())
    run = awaiting_td(subject)
    obligations = extract_prd_obligations(run.prd_draft, run.prd_blueprint)
    validate_td_obligations(
        run.td_draft,
        run.prd_draft,
        run.prd_approval,
        run.design_authority,
        run.td_blueprint,
        obligations,
    )
    permission = next(
        item for item in obligations if item.prd_section_id.value == "rules"
    )
    quote = "所有普通用户均可导出，无需管理员权限。"
    start = run.td_draft.content.index(quote)
    prd_start = run.prd_draft.content.index(permission.statement)
    conflict = finding(run) | {
        "obligation_ids": [permission.obligation_id],
        "prd_excerpt": {
            "start": prd_start,
            "end": prd_start + len(permission.statement),
            "excerpt": permission.statement,
        },
        "td_excerpt": {"start": start, "end": start + len(quote), "excerpt": quote},
    }
    blocked = subject.record_td_review(
        run.run_id,
        td_review_request(
            run, findings=[conflict], human_conclusion="changes_required"
        ),
    )
    assert blocked.td_review.status == "blocked"
    with pytest.raises(GovernanceError, match="td_review_blocked"):
        subject.approve_td(run.run_id, approval(blocked))
    assert subject.get_run(run.run_id) == blocked


def test_structure_failure_cannot_be_made_ready_by_human_review():
    # Corrupt stored domain state deliberately to exercise the guard independently of Author input.
    subject = runner()
    run = awaiting_td(subject)
    content = run.td_draft.content.replace(
        run.td_draft.obligations[0].obligation_id, "removed-id"
    )
    from hashlib import sha256

    from deliveryflow_speccraft.td_review import current_td_review_binding

    corrupt = run.model_copy(
        update={
            "td_draft": run.td_draft.model_copy(
                update={
                    "content": content,
                    "content_hash": sha256(content.encode()).hexdigest(),
                }
            )
        }
    )
    corrupt = corrupt.model_copy(
        update={
            "td_review": corrupt.td_review.model_copy(
                update={
                    "binding": current_td_review_binding(corrupt),
                }
            )
        }
    )
    corrupt = corrupt.model_copy(update={"td_revisions": (corrupt.td_draft,)})
    subject._runs[run.run_id] = corrupt
    reviewed = subject.record_td_review(run.run_id, td_review_request(corrupt))
    assert reviewed.td_review.status == "blocked"
    assert "approve_td" not in reviewed.available_commands
    from deliveryflow_speccraft.runner import TdObligationConflict

    with pytest.raises(TdObligationConflict):
        subject.approve_td(run.run_id, approval(reviewed))


@pytest.mark.parametrize(
    "changes",
    [
        {"computed_status": "ready"},
        {"human_conclusion": "no_conflict_observed"},
        {"reviewed_at": "2026-10-29T12:00:00"},
        {"findings": "duplicate"},
    ],
)
def test_review_record_rejects_inconsistent_or_untraceable_evidence(changes):
    from deliveryflow_contracts.td import TdReviewRecord
    from pydantic import ValidationError

    subject = runner()
    run = awaiting_td(subject)
    reviewed = subject.record_td_review(
        run.run_id,
        td_review_request(
            run, findings=[finding(run)], human_conclusion="changes_required"
        ),
    )
    record = reviewed.td_review_records[-1]
    if changes.get("findings") == "duplicate":
        changes = {"findings": [record.findings[0].model_dump()] * 2}
    with pytest.raises(ValidationError):
        TdReviewRecord.model_validate(record.model_dump() | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "ready"},
        {"current_review_id": "forged"},
        {"review_revision": 1},
        {"blocking_finding_ids": ["forged"]},
    ],
)
def test_missing_projection_cannot_claim_a_review_or_ready(changes):
    from deliveryflow_contracts.td import TdReviewProjection
    from pydantic import ValidationError

    subject = runner()
    run = awaiting_td(subject)
    with pytest.raises(ValidationError):
        TdReviewProjection.model_validate(run.td_review.model_dump() | changes)
