import hashlib
import json

import pytest
from deliveryflow_contracts.context import (
    ContextEntry,
    ContextMode,
    HarnessContextSlice,
    HarnessErrorCode,
    ReadStatus,
    RepositoryBinding,
    SourceRef,
    SourceSnapshot,
    SourceType,
)
from deliveryflow_contracts.runs import CreateRunRequest
from pydantic import ValidationError


def test_source_snapshot_keeps_provenance_hash_and_read_state() -> None:
    snapshot = SourceSnapshot(
        source=SourceRef(source_type=SourceType.REQUIREMENT_FILE, path="requirements/request.md"),
        normalized_path="requirements/request.md",
        sha256=hashlib.sha256("导入 Excel。".encode()).hexdigest(),
        read_status=ReadStatus.READ,
        content="导入 Excel。",
    )

    assert snapshot.model_dump(mode="json") == {
        "source": {
            "source_type": "requirement_file",
            "path": "requirements/request.md",
        },
        "normalized_path": "requirements/request.md",
        "sha256": hashlib.sha256("导入 Excel。".encode()).hexdigest(),
        "read_status": "read",
        "content": "导入 Excel。",
    }


def test_repository_binding_is_explicitly_read_only() -> None:
    binding = RepositoryBinding(
        repository_id="exportflow-sample",
        root_path="/workspace/exportflow-sample",
        context_mode=ContextMode.GUIDE_ONLY,
    )

    assert binding.permission == "read_only"


def test_context_slice_retains_selection_reason_and_hash() -> None:
    snapshot = SourceSnapshot(
        source=SourceRef(source_type=SourceType.REPOSITORY_GUIDE, path="AGENTS.md"),
        normalized_path="AGENTS.md",
        sha256=hashlib.sha256("使用分层架构。".encode()).hexdigest(),
        read_status=ReadStatus.READ,
        content="使用分层架构。",
    )
    context = HarnessContextSlice(
        entries=(ContextEntry(snapshot=snapshot, selection_reason="repository guide"),),
        sha256=hashlib.sha256(
            json.dumps(
                [
                    {
                        "path": "AGENTS.md",
                        "sha256": hashlib.sha256("使用分层架构。".encode()).hexdigest(),
                        "selection_reason": "repository guide",
                        "content": "使用分层架构。",
                    }
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    )

    assert context.entries[0].selection_reason == "repository guide"
    assert (
        context.entries[0].snapshot.sha256 == hashlib.sha256("使用分层架构。".encode()).hexdigest()
    )


def test_source_snapshot_rejects_absolute_or_traversal_paths_and_bad_hashes() -> None:
    base = {
        "source": {"source_type": "repository_guide", "path": "AGENTS.md"},
        "sha256": hashlib.sha256(b"guide").hexdigest(),
        "read_status": "read",
        "content": "guide",
    }
    with pytest.raises(ValidationError):
        SourceSnapshot(**base, normalized_path="../outside.txt")
    with pytest.raises(ValidationError):
        SourceSnapshot(**base, normalized_path="/outside.txt")
    with pytest.raises(ValidationError):
        SourceSnapshot(**{**base, "sha256": "short"}, normalized_path="AGENTS.md")
    with pytest.raises(ValidationError, match="SHA-256"):
        SourceSnapshot(**{**base, "sha256": "a" * 64}, normalized_path="AGENTS.md")


def test_create_run_accepts_exactly_one_nonblank_inline_or_file_source() -> None:
    inline = CreateRunRequest(governance_contract_version=2, requirement="  导出进度。  ")
    file = CreateRunRequest(
        governance_contract_version=2,
        requirement_path="requirements/large-excel-import.md",
    )

    assert inline.requirement == "  导出进度。  "
    assert file.requirement_path == "requirements/large-excel-import.md"
    with pytest.raises(ValidationError):
        CreateRunRequest(governance_contract_version=2, requirement=" ")
    with pytest.raises(ValidationError):
        CreateRunRequest(governance_contract_version=2, requirement_path="  ")
    with pytest.raises(ValidationError):
        CreateRunRequest(
            governance_contract_version=2,
            requirement="需求",
            requirement_path="requirements/x.md",
        )
    with pytest.raises(ValidationError):
        CreateRunRequest(
            governance_contract_version=2,
        )


def test_harness_failure_codes_are_public_and_stable() -> None:
    assert HarnessErrorCode.PATH_OUTSIDE_ROOT == "path_outside_root"
    assert HarnessErrorCode.SYMLINK_NOT_ALLOWED == "symlink_not_allowed"
    assert HarnessErrorCode.FILE_TOO_LARGE == "file_too_large"
