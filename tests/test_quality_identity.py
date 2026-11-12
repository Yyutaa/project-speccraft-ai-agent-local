"""Exact repeated observations cannot reset the stable Issue budget."""

from deliveryflow_contracts.model_tasks import ModelResources
from deliveryflow_speccraft.model_boundary import validate_task_output
from deliveryflow_speccraft.quality_engine import make_task, merge_findings
from test_quality_cycle import ScriptedModel, awaiting, subject


def test_reason_change_keeps_issue_identity_and_exhausted_budget():
    model = ScriptedModel()
    runner = subject(model)
    run = awaiting(runner)
    task = make_task(
        run, "discover", ModelResources(template="", guide="", self_check="")
    )
    output = validate_task_output(task, model.execute(task))
    observed = merge_findings(run, output)
    issue = observed.quality_issues[0].model_copy(
        update={
            "attempts": 3,
            "status": "failed",
            "last_failure": "issue_budget_exhausted",
        }
    )
    observed = observed.model_copy(update={"quality_issues": (issue,)})
    changed = output.semantic_findings[0].model_copy(
        update={"reason": "换一种描述同一个问题"}
    )
    merged = merge_findings(
        observed, output.model_copy(update={"semantic_findings": (changed,)})
    )
    assert len(merged.quality_issues) == 1
    assert merged.quality_issues[0].issue_id == issue.issue_id
    assert merged.quality_issues[0].attempts == 3
    assert merged.quality_issues[0].status == "failed"


def test_two_real_intervals_are_not_merged_even_with_same_reason():
    model = ScriptedModel()
    runner = subject(model)
    run = awaiting(runner)
    task = make_task(
        run, "discover", ModelResources(template="", guide="", self_check="")
    )
    output = validate_task_output(task, model.execute(task))
    first = output.semantic_findings[0]
    second = first.model_copy(
        update={
            "start": first.start + 1,
            "excerpt": first.excerpt[1:],
        }
    )
    output = validate_task_output(
        task,
        output.model_copy(
            update={
                "semantic_findings": (first, second),
            }
        ),
    )
    merged = merge_findings(run, output)
    assert len(merged.quality_issues) == 2
    assert len({i.issue_id for i in merged.quality_issues}) == 2
