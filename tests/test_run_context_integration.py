from pathlib import Path

from deliveryflow_contracts.context import ContextMode, SourceType
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import InMemoryRunner


def runner() -> InMemoryRunner:
    sample_root = Path(__file__).parent.parent / "examples/speccraft/repositories/exportflow-sample"
    pack = Path(__file__).parent.parent / "learning-assets/authoring-pack/v1/prd"
    return InMemoryRunner(RepositoryHarness(sample_root), pack)


def test_runner_keeps_requirement_source_separate_from_harness_context() -> None:
    response = runner().create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement_path="requirements/large-excel-import.md",
        )
    )

    assert response.source_snapshot.source.source_type is SourceType.REQUIREMENT_FILE
    assert response.source_snapshot.normalized_path == "requirements/large-excel-import.md"
    assert "Excel" in response.requirement
    assert response.prd_draft is None
    assert "分层架构" not in response.ledger.authoritative_view
    assert response.status.value == "awaiting_clarification"
    assert response.repository_binding.permission == "read_only"
    assert response.harness_context.entries
    assert all(entry.selection_reason for entry in response.harness_context.entries)


def test_runner_hashes_raw_inline_text_but_generates_prd_from_trimmed_requirement() -> None:
    raw = "  导出进度。  "
    response = runner().create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement=raw,
            context_mode=ContextMode.GUIDE_ONLY,
        )
    )

    assert response.source_snapshot.content == raw
    assert response.requirement == "导出进度。"
    assert response.source_snapshot.source.source_type is SourceType.INLINE_REQUIREMENT
    assert [entry.snapshot.normalized_path for entry in response.harness_context.entries] == [
        "AGENTS.md",
        "README.md",
    ]
