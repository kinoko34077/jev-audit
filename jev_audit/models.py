from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
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
    issue_areas: dict[str, str]
    status_criteria: dict[str, str]


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    content: str
    chars: int
    original_chars: int
    truncated: bool


@dataclass(frozen=True)
class ScanResult:
    root: str
    files: tuple[FileSnapshot, ...]
    skipped_counts: dict[str, int]
    skipped_sensitive_paths: tuple[str, ...]
    git: dict[str, Any]


@dataclass(frozen=True)
class Batch:
    index: int
    files: tuple[FileSnapshot, ...]

    @property
    def chars(self) -> int:
        return sum(item.chars for item in self.files)

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
    scores: dict[str, dict[str, Any]]


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
    final: JevResult

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def status(self) -> str:
        choice = self.final.choices.get("overall_status", {}).get("choice")
        return str(choice or "unknown")
