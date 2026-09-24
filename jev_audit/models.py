from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuditRule:
    id: str
    title: str
    description: str


@dataclass(frozen=True)
class AuditProfile:
    name: str
    description: str
    rules: tuple[AuditRule, ...]
    status_criteria: dict[str, str]
    source: str = ""
    source_sha256: str = ""


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    content: str
    chars: int
    original_chars: int
    truncated: bool
    change: str = ""


@dataclass(frozen=True)
class ScanResult:
    root: str
    files: tuple[FileSnapshot, ...]
    skipped_counts: dict[str, int]
    skipped_sensitive_paths: tuple[str, ...]
    git: dict[str, Any]
    skipped_paths_by_reason: dict[str, tuple[str, ...]] = field(default_factory=dict)
    excluded_directories: tuple[str, ...] = ()


@dataclass(frozen=True)
class Batch:
    index: int
    files: tuple[FileSnapshot, ...]

    @property
    def chars(self) -> int:
        return sum(item.chars + len(item.change) for item in self.files)

    @property
    def paths(self) -> list[str]:
        return [item.path for item in self.files]


@dataclass(frozen=True)
class JevResult:
    model: str
    elapsed_ms: float
    usage: dict[str, int | None]
    choices: dict[str, dict[str, Any]]
    nouls: dict[str, float]


@dataclass(frozen=True)
class BatchAudit:
    index: int
    paths: tuple[str, ...]
    chars: int
    result: JevResult


@dataclass(frozen=True)
class AuditReport:
    root: str
    profile: str
    files_scanned: int
    batches: int
    skipped_counts: dict[str, int]
    skipped_sensitive_paths: tuple[str, ...]
    git: dict[str, Any]
    batch_audits: tuple[BatchAudit, ...]
    aggregate: dict[str, Any]
    truncated_paths: tuple[str, ...] = ()
    skipped_paths_by_reason: dict[str, tuple[str, ...]] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    excluded_directories: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def status(self) -> str:
        return str(self.aggregate.get("overall", {}).get("status") or "unknown")

    @property
    def model(self) -> str:
        if not self.batch_audits:
            return "unknown"
        return self.batch_audits[0].result.model
