"""Entry points share server-selected resources and validated model boundaries."""

import importlib
import json
import sys
from pathlib import Path

import pytest
from deliveryflow_contracts.model_tasks import ModelTaskInput, ModelTaskOutput
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.model_boundary import ModelBoundaryError
from deliveryflow_speccraft.runner import FakeProvider

ROOT = Path(__file__).resolve().parents[1]


class SuggestedClarifications:
    def propose_clarifications(self, task: ModelTaskInput) -> ModelTaskOutput:
        result = FakeProvider().propose_clarifications(task)
        return result.model_copy(
            update={
                "proposals": tuple(
                    p.model_copy(update={"question": "请明确这个维度的产品规则。"})
                    for p in result.proposals
                ),
            }
        )


def test_composed_clarification_model_only_proposes_and_never_confirms_facts(tmp_path):
    composition = importlib.import_module("deliveryflow_speccraft.composition")
    runner = composition.build_runner(
        ROOT,
        database_path=tmp_path / "runs.sqlite3",
        clarification_provider=SuggestedClarifications(),
    )
    run = runner.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="创建导出工具。",
        )
    )
    assert run.clarification_batch.proposals
    assert all(
        p.question == "请明确这个维度的产品规则。"
        for p in run.clarification_batch.proposals
    )
    assert not run.ledger.facts
    assert run.prd_draft is None
    assert not run.completeness.is_complete


def test_composed_model_invalid_binding_does_not_leave_a_run(tmp_path):
    composition = importlib.import_module("deliveryflow_speccraft.composition")

    class WrongBinding(SuggestedClarifications):
        def propose_clarifications(self, task):
            return (
                super()
                .propose_clarifications(task)
                .model_copy(
                    update={"input_binding": "0" * 64},
                )
            )

    runner = composition.build_runner(
        ROOT,
        database_path=tmp_path / "runs.sqlite3",
        clarification_provider=WrongBinding(),
    )
    with pytest.raises(ModelBoundaryError):
        runner.create_run(
            CreateRunRequest(
                governance_contract_version=2,
                requirement="创建导出工具。",
            )
        )
    assert runner.list_run_ids() == ()


def test_composed_runners_read_the_same_persistent_authority(tmp_path):
    composition = importlib.import_module("deliveryflow_speccraft.composition")
    database = tmp_path / "runs.sqlite3"
    first = composition.build_runner(ROOT, database_path=database)
    run = first.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="创建导出工具。",
        )
    )
    second = composition.build_runner(ROOT, database_path=database)
    assert second.get_run(run.run_id) == run
    assert second.get_run(run.run_id).source_snapshot == run.source_snapshot


def test_cli_reads_persistent_summary_without_exposing_source_text(
    tmp_path, monkeypatch, capsys
):
    composition = importlib.import_module("deliveryflow_speccraft.composition")
    from apps.cli.__main__ import main

    database = tmp_path / "runs.sqlite3"
    runner = composition.build_runner(ROOT, database_path=database)
    run = runner.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="此原始需求不属于状态摘要。",
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "speccraft",
            "--run-id",
            run.run_id,
            "--database",
            str(database),
        ],
    )
    main()
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["run_id"] == run.run_id
    assert summary["status"] == "awaiting_clarification"
    assert summary["available_commands"] == ["submit_clarification"]
    assert run.requirement not in output
    assert runner.get_run(run.run_id) == run
