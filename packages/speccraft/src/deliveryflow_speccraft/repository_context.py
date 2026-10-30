"""Bounded, read-only source capture for the ExportFlow teaching fixture."""

import errno
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import NamedTuple

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

MAX_SOURCE_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 128 * 1024
_GUIDE_FILES = ("AGENTS.md", "README.md")
_INDEXED_FILES = (".deliveryflow/repository.yaml", "package.json", "pyproject.toml")
_DENIED_DIRECTORIES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".next", "dist", "build",
    "coverage", ".deliveryflow-local", ".deliveryflow-state", ".secrets", ".ssh", ".aws",
    "secrets", "credentials", "tokens", "keys", "certs", "private",
}
_DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}
_ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".toml", ".yaml", ".yml"}
_ALLOWED_NAMES = {"agents.md", "readme", "readme.md", "license", "notice"}


class HarnessReadError(Exception):
    def __init__(self, code: HarnessErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class RunContext(NamedTuple):
    requirement: SourceSnapshot
    binding: RepositoryBinding
    context: HarnessContextSlice


class RepositoryHarness:
    """Reads only an explicitly configured fixture root; never writes to it."""

    def __init__(self, allowed_root: Path, repository_id: str = "exportflow-sample") -> None:
        try:
            if allowed_root.is_symlink():
                raise HarnessReadError(HarnessErrorCode.SYMLINK_NOT_ALLOWED)
            root = allowed_root.resolve(strict=True)
        except OSError as error:
            raise HarnessReadError(HarnessErrorCode.REPOSITORY_NOT_ALLOWED) from error
        if not root.is_dir():
            raise HarnessReadError(HarnessErrorCode.REPOSITORY_NOT_ALLOWED)
        self.root = root
        self.repository_id = repository_id

    def build(self, request: CreateRunRequest) -> RunContext:
        if request.requirement_path is not None and (
            self._validated_parts(request.requirement_path)[0] != "requirements"
            or not request.requirement_path.lower().endswith(".md")
        ):
            raise HarnessReadError(HarnessErrorCode.PATH_NOT_ALLOWED)
        requirement = (
            self.read_source(request.requirement_path, SourceType.REQUIREMENT_FILE)
            if request.requirement_path is not None
            else self._inline_requirement(request.requirement or "")
        )
        if not requirement.content.strip():
            raise HarnessReadError(HarnessErrorCode.EMPTY_REQUIREMENT)
        mode = ContextMode(request.context_mode)
        paths = _GUIDE_FILES + (_INDEXED_FILES if mode is ContextMode.INDEXED_READONLY else ())
        entries = tuple(
            ContextEntry(
                snapshot=self.read_source(
                    relative_path,
                    SourceType.REPOSITORY_GUIDE
                    if relative_path in _GUIDE_FILES
                    else SourceType.REPOSITORY_METADATA,
                ),
                selection_reason=(
                    "repository guide supplies engineering constraints"
                    if relative_path in _GUIDE_FILES
                    else "indexed repository metadata describes the declared stack"
                ),
            )
            for relative_path in paths
        )
        digest_payload = [
            {
                "path": entry.snapshot.normalized_path,
                "sha256": entry.snapshot.sha256,
                "selection_reason": entry.selection_reason,
                "content": entry.snapshot.content,
            }
            for entry in entries
        ]
        canonical = json.dumps(
            digest_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(canonical) > MAX_CONTEXT_BYTES:
            raise HarnessReadError(HarnessErrorCode.CONTEXT_TOO_LARGE)
        context = HarnessContextSlice(entries=entries, sha256=hashlib.sha256(canonical).hexdigest())
        binding = RepositoryBinding(
            repository_id=self.repository_id,
            root_path=str(self.root),
            context_mode=mode,
        )
        return RunContext(requirement=requirement, binding=binding, context=context)

    def read_knowledge(self, relative_path: str) -> SourceSnapshot:
        parts = self._validated_parts(relative_path)
        if len(parts) < 2 or parts[0] != "knowledge":
            raise HarnessReadError(HarnessErrorCode.PATH_NOT_ALLOWED)
        return self.read_source(relative_path, SourceType.BUSINESS_KNOWLEDGE)

    def read_source(self, relative_path: str, source_type: SourceType) -> SourceSnapshot:
        parts = self._validated_parts(relative_path)
        if any(part.lower() in _DENIED_DIRECTORIES for part in parts[:-1]):
            raise HarnessReadError(HarnessErrorCode.PATH_NOT_ALLOWED)
        filename = parts[-1]
        lower_name = filename.lower()
        suffix = Path(filename).suffix.lower()
        if (
            lower_name == ".env"
            or lower_name.startswith(".env.")
            or lower_name.startswith("credentials")
            or lower_name.startswith("secret")
            or lower_name.startswith("token")
            or suffix in _DENIED_SUFFIXES
            or (lower_name not in _ALLOWED_NAMES and suffix not in _ALLOWED_SUFFIXES)
        ):
            raise HarnessReadError(HarnessErrorCode.PATH_NOT_ALLOWED)

        candidate = self.root
        for part in parts:
            candidate = candidate / part
            try:
                if candidate.is_symlink():
                    raise HarnessReadError(HarnessErrorCode.SYMLINK_NOT_ALLOWED)
                candidate.lstat()
            except FileNotFoundError as error:
                raise HarnessReadError(HarnessErrorCode.SOURCE_NOT_FOUND) from error
            except OSError as error:
                raise HarnessReadError(HarnessErrorCode.SOURCE_UNREADABLE) from error

        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
            parent_descriptor = os.open(self.root, directory_flags)
            try:
                for part in parts[:-1]:
                    next_descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
                    os.close(parent_descriptor)
                    parent_descriptor = next_descriptor
                descriptor = os.open(parts[-1], flags, dir_fd=parent_descriptor)
            finally:
                os.close(parent_descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                os.close(descriptor)
                raise HarnessReadError(HarnessErrorCode.UNSUPPORTED_FILE)
            if metadata.st_size > MAX_SOURCE_BYTES:
                os.close(descriptor)
                raise HarnessReadError(HarnessErrorCode.FILE_TOO_LARGE)
            with os.fdopen(descriptor, "rb") as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
        except HarnessReadError:
            raise
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise HarnessReadError(HarnessErrorCode.SYMLINK_NOT_ALLOWED) from error
            if isinstance(error, FileNotFoundError):
                raise HarnessReadError(HarnessErrorCode.SOURCE_NOT_FOUND) from error
            raise HarnessReadError(HarnessErrorCode.SOURCE_UNREADABLE) from error
        if len(raw) > MAX_SOURCE_BYTES:
            raise HarnessReadError(HarnessErrorCode.FILE_TOO_LARGE)
        if b"\x00" in raw:
            raise HarnessReadError(HarnessErrorCode.UNSUPPORTED_FILE)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HarnessReadError(HarnessErrorCode.UNSUPPORTED_FILE) from error
        normalized = PurePosixPath(*parts).as_posix()
        return SourceSnapshot(
            source=SourceRef(source_type=source_type, path=relative_path),
            normalized_path=normalized,
            sha256=hashlib.sha256(raw).hexdigest(),
            read_status=ReadStatus.READ,
            content=content,
        )

    def _validated_parts(self, relative_path: str) -> tuple[str, ...]:
        if not relative_path or "\x00" in relative_path or "\\" in relative_path:
            raise HarnessReadError(HarnessErrorCode.INVALID_SOURCE_PATH)
        path = PurePosixPath(relative_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.split("/")):
            raise HarnessReadError(HarnessErrorCode.PATH_OUTSIDE_ROOT)
        return path.parts

    @staticmethod
    def _inline_requirement(requirement: str) -> SourceSnapshot:
        raw = requirement.encode("utf-8")
        if len(raw) > MAX_SOURCE_BYTES:
            raise HarnessReadError(HarnessErrorCode.FILE_TOO_LARGE)
        return SourceSnapshot(
            source=SourceRef(source_type=SourceType.INLINE_REQUIREMENT),
            sha256=hashlib.sha256(raw).hexdigest(),
            read_status=ReadStatus.READ,
            content=requirement,
        )
