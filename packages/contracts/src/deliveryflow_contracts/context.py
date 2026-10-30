"""Public contracts for trusted input and read-only repository context."""

import hashlib
import json
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceType(StrEnum):
    BUSINESS_KNOWLEDGE = "business_knowledge"
    INLINE_REQUIREMENT = "inline_requirement"
    REQUIREMENT_FILE = "requirement_file"
    REPOSITORY_GUIDE = "repository_guide"
    REPOSITORY_METADATA = "repository_metadata"


class ReadStatus(StrEnum):
    READ = "read"


class ContextMode(StrEnum):
    GUIDE_ONLY = "guide_only"
    INDEXED_READONLY = "indexed_readonly"


class HarnessErrorCode(StrEnum):
    INVALID_SOURCE_PATH = "invalid_source_path"
    PATH_OUTSIDE_ROOT = "path_outside_root"
    PATH_NOT_ALLOWED = "path_not_allowed"
    SYMLINK_NOT_ALLOWED = "symlink_not_allowed"
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_UNREADABLE = "source_unreadable"
    UNSUPPORTED_FILE = "unsupported_file"
    FILE_TOO_LARGE = "file_too_large"
    CONTEXT_TOO_LARGE = "context_too_large"
    EMPTY_REQUIREMENT = "empty_requirement"
    REPOSITORY_NOT_ALLOWED = "repository_not_allowed"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    path: str | None = None


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceRef
    normalized_path: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_status: ReadStatus
    content: str

    @field_validator("normalized_path")
    @classmethod
    def require_normalized_relative_path(cls, value: str | None) -> str | None:
        if value is not None:
            normalized = PurePosixPath(value)
            if (
                normalized.is_absolute()
                or PureWindowsPath(value).drive
                or "\\" in value
                or normalized.as_posix() != value
                or ".." in normalized.parts
            ):
                raise ValueError(
                    "normalized_path must be normalized and relative to its trusted root"
                )
        return value

    @model_validator(mode="after")
    def validate_content_hash(self) -> "SourceSnapshot":
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("source SHA-256 must match the captured UTF-8 content")
        return self


class RepositoryBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repository_id: str = Field(min_length=1)
    root_path: str = Field(min_length=1)
    permission: Literal["read_only"] = "read_only"
    context_mode: ContextMode


class ContextEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: SourceSnapshot
    selection_reason: str = Field(min_length=1)


class HarnessContextSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[ContextEntry, ...]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_slice_hash(self) -> "HarnessContextSlice":
        payload = [
            {
                "path": entry.snapshot.normalized_path,
                "sha256": entry.snapshot.sha256,
                "selection_reason": entry.selection_reason,
                "content": entry.snapshot.content,
            }
            for entry in self.entries
        ]
        canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != self.sha256:
            raise ValueError("context SHA-256 must match its ordered entries")
        return self
