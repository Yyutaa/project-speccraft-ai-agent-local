import pytest
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    DuplicateCommand,
    GovernanceError,
    RevisionConflict,
    RunNotFound,
)
from governance_helpers import td_review_request
from test_td_review import approval, awaiting_td, finding
from test_td_runner import runner


def revision_request(run, **changes):
    from deliveryflow_contracts.td import TdRevisionRequest

    return TdRevisionRequest.model_validate(
        {
            "governance_contract_version": 2,
            "command_id": "revise-1",
            "section_id": "frontend",
            "replacement_body": "前端按已冻结权限显示导出入口。",
            "feedback": "明确前端实现",
            "actor_claim": "owner",
            "expected_td_revision": run.td_draft.revision,
            "expected_td_content_hash": run.td_draft.content_hash,
            "expected_review_revision": run.td_review.review_revision,
            **changes,
        }
    )


def blocked_run(subject):
    run = awaiting_td(subject)
    return subject.record_td_review(
        run.run_id,
        td_review_request(
            run, findings=[finding(run)], human_conclusion="changes_required"
        ),
    )


def test_single_section_revision_preserves_bindings_history_and_invalidates_review():
    subject = runner()
    ready = subject.record_td_review(
        (run := awaiting_td(subject)).run_id, td_review_request(run)
    )
    old_approval = approval(ready)
    revised = subject.revise_td(ready.run_id, revision_request(ready))
    assert revised.td_draft.revision == 2
    assert revised.td_revisions == (ready.td_draft, revised.td_draft)
    assert revised.td_readiness.ready
    assert revised.td_review.status == "stale"
    assert revised.td_review.review_revision == 2
    assert revised.td_review_records == ready.td_review_records
    assert (
        revised.prd_draft == ready.prd_draft
        and revised.prd_approval == ready.prd_approval
    )
    assert revised.design_authority == ready.design_authority
    assert revised.technical_decisions == ready.technical_decisions
    assert revised.td_draft.obligations == ready.td_draft.obligations
    prefix, suffix = ready.td_draft.content.split(
        "## 前端页面、组件、交互与状态管理\n", 1
    )
    suffix = suffix[suffix.index("## API、事件与错误契约") :]
    assert revised.td_draft.content.startswith(
        prefix + "## 前端页面、组件、交互与状态管理\n"
    )
    assert revised.td_draft.content.endswith(suffix)
    with pytest.raises(RevisionConflict):
        subject.approve_td(ready.run_id, old_approval)
    reviewed = subject.record_td_review(
        ready.run_id, td_review_request(revised, "review-2")
    )
    assert reviewed.td_review.review_revision == 3
    assert (
        subject.approve_td(ready.run_id, approval(reviewed)).td_approval.revision == 2
    )


@pytest.mark.parametrize("outcome", ["fixed", "not_applicable", "still_present"])
def test_new_revision_rechecks_preserve_old_excerpts_and_require_current_evidence(
    outcome,
):
    subject = runner()
    blocked = blocked_run(subject)
    revised = subject.revise_td(blocked.run_id, revision_request(blocked))
    with pytest.raises(GovernanceError, match="invalid_td_review"):
        subject.record_td_review(revised.run_id, td_review_request(revised, "recheck"))
    recheck = {
        "finding_id": "permission-conflict",
        "outcome": outcome,
        "rationale": "人工逐条复查",
    }
    if outcome == "still_present":
        recheck["td_excerpt"] = {
            "start": 0,
            "end": 10,
            "excerpt": revised.td_draft.content[:10],
        }
    reviewed = subject.record_td_review(
        revised.run_id,
        td_review_request(
            revised,
            "recheck",
            rechecks=[recheck],
            human_conclusion="changes_required"
            if outcome == "still_present"
            else "no_conflict_observed",
        ),
    )
    assert reviewed.td_review.status == (
        "blocked" if outcome == "still_present" else "ready"
    )
    assert (
        reviewed.td_review_records[-1].findings[0].td_excerpt
        == blocked.td_review_records[-1].findings[0].td_excerpt
    )
    # Later reviews use retained historical evidence, even if old offsets no longer match.
    changes = (
        {}
        if outcome != "still_present"
        else {
            "existing_finding_dispositions": [
                {
                    "finding_id": "permission-conflict",
                    "disposition": "dismissed",
                    "disposition_rationale": "误报",
                }
            ]
        }
    )
    assert (
        subject.record_td_review(
            reviewed.run_id, td_review_request(reviewed, "again", **changes)
        ).td_review.status
        == "ready"
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"expected_td_revision": 9}, "revision_conflict"),
        ({"expected_td_content_hash": "0" * 64}, "content_hash_conflict"),
        ({"expected_review_revision": 9}, "td_review_conflict"),
        ({"replacement_body": "## 外来章节"}, "invalid_td_revision"),
    ],
)
def test_revision_failure_is_atomic_and_does_not_consume_command(change, code):
    subject = runner()
    run = blocked_run(subject)
    with pytest.raises(
        (GovernanceError, RevisionConflict, ContentHashConflict)
    ) as failure:
        subject.revise_td(run.run_id, revision_request(run, **change))
    assert code in str(failure.value) or failure.value.__class__.__name__ in {
        "RevisionConflict",
        "ContentHashConflict",
    }
    assert subject.get_run(run.run_id) == run
    updated = subject.revise_td(run.run_id, revision_request(run))
    with pytest.raises(DuplicateCommand, match="revise-1"):
        subject.revise_td(run.run_id, revision_request(updated))


def test_revision_before_first_review_and_structural_readiness_blocks_approval():
    subject = runner()
    run = awaiting_td(subject)
    revised = subject.revise_td(
        run.run_id, revision_request(run, replacement_body="TODO")
    )
    assert (
        revised.td_review.status == "stale"
        and revised.td_review.current_review_id is None
    )
    assert not revised.td_readiness.ready
    reviewed = subject.record_td_review(run.run_id, td_review_request(revised))
    assert reviewed.td_review.status == "blocked"
    assert "approve_td" not in reviewed.available_commands


def test_product_change_parent_run_is_trace_only_and_unknown_parent_fails_atomically():
    subject = runner()
    run = awaiting_td(subject)
    product = finding(run) | {"disposition": "product_change_required"}
    blocked = subject.record_td_review(
        run.run_id,
        td_review_request(
            run, findings=[product], human_conclusion="product_change_required"
        ),
    )
    child = subject.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="用户提供新的需求",
            parent_run_id=run.run_id,
        )
    )
    assert child.parent_run_id == run.run_id and child.ledger.facts == ()
    assert child.prd_approval is None and child.artifact_envelopes == ()
    assert subject.get_run(run.run_id) == blocked
    count = len(subject._runs)
    with pytest.raises(RunNotFound):
        subject.create_run(
            CreateRunRequest(
                governance_contract_version=2,
                requirement="新需求",
                parent_run_id="missing",
            )
        )
    assert len(subject._runs) == count


def test_fixed_requires_actual_content_change_and_still_present_requires_current_excerpt():
    subject = runner()
    blocked = blocked_run(subject)
    # Return the same body with identical canonical whitespace: revision advances, hash does not.
    content = blocked.td_draft.content
    start = content.index("## 前端页面、组件、交互与状态管理\n")
    body = content[start:].split("\n", 1)[1].split("## API、事件与错误契约")[0].strip()
    revised = subject.revise_td(
        blocked.run_id, revision_request(blocked, replacement_body=body)
    )
    assert revised.td_draft.content_hash == blocked.td_draft.content_hash
    for recheck in [
        {"finding_id": "permission-conflict", "outcome": "fixed", "rationale": "改了"},
        {
            "finding_id": "permission-conflict",
            "outcome": "still_present",
            "rationale": "仍有",
        },
        {
            "finding_id": "permission-conflict",
            "outcome": "still_present",
            "rationale": "仍有",
            "td_excerpt": {"start": 0, "end": 3, "excerpt": "伪造文"},
        },
    ]:
        with pytest.raises(GovernanceError, match="invalid_td_review"):
            subject.record_td_review(
                revised.run_id, td_review_request(revised, "retry", rechecks=[recheck])
            )
        assert subject.get_run(revised.run_id) == revised
    dismissed = {
        "finding_id": "permission-conflict",
        "outcome": "not_applicable",
        "rationale": "人工确认原摘录为误报",
    }
    assert (
        subject.record_td_review(
            revised.run_id, td_review_request(revised, "retry", rechecks=[dismissed])
        ).td_review.status
        == "ready"
    )


def test_historical_quotes_are_verified_against_original_revision_not_current_text():
    from deliveryflow_contracts.runs import RunResponse
    from pydantic import ValidationError

    subject = runner()
    run = awaiting_td(subject)
    item = finding(run)
    quote = "## API、事件与错误契约"
    start = run.td_draft.content.index(quote)
    item["td_excerpt"] = {"start": start, "end": start + len(quote), "excerpt": quote}
    blocked = subject.record_td_review(
        run.run_id,
        td_review_request(run, findings=[item], human_conclusion="changes_required"),
    )
    revised = subject.revise_td(run.run_id, revision_request(blocked))
    reviewed = subject.record_td_review(
        run.run_id,
        td_review_request(
            revised,
            "again",
            rechecks=[
                {
                    "finding_id": item["finding_id"],
                    "outcome": "fixed",
                    "rationale": "已逐项核查修订",
                }
            ],
        ),
    )
    assert RunResponse.model_validate(reviewed.model_dump()) == reviewed
    payload = reviewed.model_dump()
    payload["td_review_records"][-1]["findings"][0]["td_excerpt"] = {
        "start": 0,
        "end": 3,
        "excerpt": "伪造文",
    }
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_ready_projection_cannot_ignore_current_structural_issues():
    from deliveryflow_contracts.runs import RunResponse
    from pydantic import ValidationError

    subject = runner()
    run = awaiting_td(subject)
    revised = subject.revise_td(
        run.run_id, revision_request(run, replacement_body="TODO")
    )
    blocked = subject.record_td_review(run.run_id, td_review_request(revised))
    payload = blocked.model_dump()
    payload["td_review_records"][-1]["computed_status"] = "ready"
    payload["td_review"]["status"] = "ready"
    payload["available_commands"] = ["record_td_review", "revise_td", "approve_td"]
    with pytest.raises(ValidationError):
        RunResponse.model_validate(payload)


def test_revision_cannot_remove_frozen_obligation_and_frozen_documents_reject_revisions():
    from deliveryflow_contracts.td import TD_SECTION_TITLES
    from deliveryflow_speccraft.runner import InvalidRunTransition

    subject = runner()
    run = awaiting_td(subject)
    obligation = run.td_draft.obligations[0].obligation_id
    # The existing structure guard requires every obligation ID somewhere in the TD.
    # Remove its references section by section; only the final removal must fail.
    for section in run.td_blueprint.sections:
        content = run.td_draft.content
        title = "## " + TD_SECTION_TITLES[section.section_id] + "\n"
        section_body = content.split(title, 1)[1].split("\n## ", 1)[0].strip()
        if obligation not in section_body:
            continue
        request = revision_request(
            run,
            section_id=section.section_id,
            command_id=f"remove-{section.section_id}",
            replacement_body=section_body.replace(obligation, "removed"),
        )
        if content.count(obligation) == section_body.count(obligation):
            with pytest.raises(GovernanceError, match="invalid_td_revision"):
                subject.revise_td(run.run_id, request)
            assert subject.get_run(run.run_id) == run
            break
        run = subject.revise_td(run.run_id, request)
    else:
        pytest.fail("the final frozen obligation reference was erased")
    reviewed = subject.record_td_review(run.run_id, td_review_request(run))
    done = subject.approve_td(run.run_id, approval(reviewed))
    with pytest.raises(InvalidRunTransition):
        subject.revise_td(run.run_id, revision_request(done))
    assert subject.get_run(run.run_id) == done
