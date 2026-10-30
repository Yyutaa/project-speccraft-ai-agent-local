import hashlib
from pathlib import Path

import pytest
from deliveryflow_contracts.context import ContextMode, SourceType
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.repository_context import (
    MAX_SOURCE_BYTES,
    HarnessReadError,
    RepositoryHarness,
)


def repository(tmp_path: Path) -> Path:
    tmp_path.mkdir()
    (tmp_path / "AGENTS.md").write_text("Use layers.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Sample repository.\n", encoding="utf-8")
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "request.md").write_text("Import Excel.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"sample"}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (tmp_path / ".deliveryflow").mkdir()
    (tmp_path / ".deliveryflow" / "repository.yaml").write_text(
        "schema_version: '1'\n", encoding="utf-8"
    )
    return tmp_path


def test_requirement_file_and_context_slice_have_stable_auditable_hashes(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    harness = RepositoryHarness(root, repository_id="sample")
    request = CreateRunRequest(
        governance_contract_version=2,
        requirement_path="requirements/request.md",
        context_mode=ContextMode.INDEXED_READONLY,
    )

    first = harness.build(request)
    second = harness.build(request)

    assert first.requirement.content == "Import Excel.\n"
    assert first.requirement.source.source_type is SourceType.REQUIREMENT_FILE
    assert first.requirement.normalized_path == "requirements/request.md"
    assert first.requirement.sha256 == hashlib.sha256(b"Import Excel.\n").hexdigest()
    assert first.context.sha256 == second.context.sha256
    assert [entry.snapshot.normalized_path for entry in first.context.entries] == [
        "AGENTS.md",
        "README.md",
        ".deliveryflow/repository.yaml",
        "package.json",
        "pyproject.toml",
    ]
    assert all(entry.selection_reason for entry in first.context.entries)
    assert first.binding.permission == "read_only"


def test_guide_only_excludes_indexed_metadata(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    result = RepositoryHarness(root, repository_id="sample").build(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="inline demand",
            context_mode=ContextMode.GUIDE_ONLY,
        )
    )

    assert [entry.snapshot.normalized_path for entry in result.context.entries] == [
        "AGENTS.md",
        "README.md",
    ]


@pytest.mark.parametrize(
    "relative_path",
    ["../outside.txt", "requirements/../../outside.txt", "/tmp/outside.txt"],
)
def test_path_traversal_and_absolute_paths_are_rejected_before_read(
    tmp_path: Path, relative_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    harness = RepositoryHarness(root, repository_id="sample")

    def unexpected_open(*args: object, **kwargs: object) -> int:
        raise AssertionError("rejected paths must not open file contents")

    monkeypatch.setattr("deliveryflow_speccraft.repository_context.os.open", unexpected_open)
    with pytest.raises(HarnessReadError, match="path_outside_root"):
        harness.read_source(relative_path, SourceType.REQUIREMENT_FILE)


def test_symlink_is_rejected_before_target_contents_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo")
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    (root / "requirements" / "linked.md").symlink_to(outside)
    harness = RepositoryHarness(root, repository_id="sample")

    def unexpected_open(*args: object, **kwargs: object) -> int:
        raise AssertionError("symlinks must be rejected before opening contents")

    monkeypatch.setattr("deliveryflow_speccraft.repository_context.os.open", unexpected_open)
    with pytest.raises(HarnessReadError, match="symlink_not_allowed"):
        harness.read_source("requirements/linked.md", SourceType.REQUIREMENT_FILE)


def test_symlink_parent_directory_is_rejected_before_target_contents_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo")
    external = tmp_path / "external"
    external.mkdir()
    (external / "request.md").write_text("secret", encoding="utf-8")
    (root / "requirements").rename(root / "requirements.original")
    (root / "requirements").symlink_to(external, target_is_directory=True)

    def unexpected_open(*args: object, **kwargs: object) -> int:
        raise AssertionError("symlink parent must be rejected before opening contents")

    monkeypatch.setattr("deliveryflow_speccraft.repository_context.os.open", unexpected_open)
    with pytest.raises(HarnessReadError, match="symlink_not_allowed"):
        RepositoryHarness(root, repository_id="sample").read_source(
            "requirements/request.md", SourceType.REQUIREMENT_FILE
        )


@pytest.mark.parametrize(
    "relative_path",
    [".env", ".git/config", "node_modules/pkg/README.md", "secrets/credentials.md"],
)
def test_sensitive_and_excluded_paths_are_rejected(tmp_path: Path, relative_path: str) -> None:
    root = repository(tmp_path / "repo")
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("secret", encoding="utf-8")

    with pytest.raises(HarnessReadError, match="path_not_allowed"):
        RepositoryHarness(root, repository_id="sample").read_source(
            relative_path, SourceType.REPOSITORY_GUIDE
        )


def test_oversized_and_non_utf8_files_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo")
    (root / "requirements" / "large.md").write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    (root / "requirements" / "invalid.md").write_bytes(b"\xff")
    harness = RepositoryHarness(root, repository_id="sample")

    def unexpected_read(*args: object, **kwargs: object) -> int:
        raise AssertionError("oversized file must be rejected before reading contents")

    with monkeypatch.context() as context:
        context.setattr("deliveryflow_speccraft.repository_context.os.fdopen", unexpected_read)
        with pytest.raises(HarnessReadError, match="file_too_large"):
            harness.read_source("requirements/large.md", SourceType.REQUIREMENT_FILE)
    with pytest.raises(HarnessReadError, match="unsupported_file"):
        harness.read_source("requirements/invalid.md", SourceType.REQUIREMENT_FILE)


def test_binary_text_file_is_rejected(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    (root / "requirements" / "binary.md").write_bytes(b"header\x00payload")

    with pytest.raises(HarnessReadError, match="unsupported_file"):
        RepositoryHarness(root, repository_id="sample").read_source(
            "requirements/binary.md", SourceType.REQUIREMENT_FILE
        )


def test_total_context_limit_rejects_without_returning_a_partial_slice(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repo")
    for relative_path in (
        "AGENTS.md",
        "README.md",
        ".deliveryflow/repository.yaml",
        "package.json",
        "pyproject.toml",
    ):
        (root / relative_path).write_text("x" * 40_000, encoding="utf-8")

    with pytest.raises(HarnessReadError, match="context_too_large"):
        RepositoryHarness(root, repository_id="sample").build(
            CreateRunRequest(governance_contract_version=2, requirement="inline request")
        )
