from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from . import __version__
from .models import AuditReport


HISTORY_SCHEMA_VERSION = 1
DEFAULT_HISTORY_PATH = Path.home() / ".jev-audit" / "history.jsonl"
HISTORY_TAIL_BYTES = 256 * 1024
ROLLING_WINDOW = 10


@dataclass(frozen=True)
class HistoryState:
    next_fixture_index: int
    recent_scores: tuple[int | None, ...]


def _read_tail(path: Path, max_bytes: int = HISTORY_TAIL_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            data = handle.read()
    except (FileNotFoundError, OSError):
        return ""
    if start > 0:
        _, separator, data = data.partition(b"\n")
        if not separator:
            return ""
    return data.decode("utf-8", errors="replace")


def read_history_state(
    path: str | Path = DEFAULT_HISTORY_PATH,
    fixture_ids: Iterable[str] = (),
) -> HistoryState:
    fixture_ids = tuple(fixture_ids)
    indexes = {fixture_id: index for index, fixture_id in enumerate(fixture_ids)}
    scores: list[int | None] = []
    last_index: int | None = None
    for line in _read_tail(Path(path)).splitlines():
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        benchmark = record.get("benchmark")
        if not isinstance(benchmark, dict):
            continue
        fixture_id = benchmark.get("fixture_id")
        if fixture_id not in indexes:
            continue
        score = benchmark.get("score")
        if score not in (0, 100, None):
            continue
        last_index = indexes[fixture_id]
        scores.append(score)
    next_index = 0 if last_index is None or not fixture_ids else (last_index + 1) % len(fixture_ids)
    return HistoryState(
        next_fixture_index=next_index,
        recent_scores=tuple(scores[-ROLLING_WINDOW:]),
    )


def rolling_mean(scores: Iterable[int | None]) -> float | None:
    numeric = [value for value in scores if value in (0, 100)]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _timestamp_now() -> str:
    value = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return value.replace("+00:00", "Z")


def build_history_record(
    report: AuditReport,
    *,
    surface: str,
    benchmark: dict,
    timestamp: str | None = None,
) -> dict:
    if surface not in {"cli", "local_mcp"}:
        raise ValueError("surface must be cli or local_mcp")
    overall = report.aggregate.get("overall", {})
    usage = report.aggregate.get("usage", {})
    provenance = report.provenance or {}
    safe_usage = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "input_tokens_complete": bool(usage.get("input_tokens_complete", False)),
        "output_tokens_complete": bool(usage.get("output_tokens_complete", False)),
    }
    safe_benchmark = {
        "fixture_id": benchmark.get("fixture_id"),
        "score": benchmark.get("score"),
        "error": benchmark.get("error"),
        "recent_scores": list(benchmark.get("recent_scores", []))[-ROLLING_WINDOW:],
        "recent_mean": benchmark.get("recent_mean"),
    }
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "timestamp": timestamp or _timestamp_now(),
        "surface": surface,
        "profile": report.profile,
        "status": str(overall.get("status") or "unknown"),
        "risk": float(overall.get("risk") or 0.0),
        "files_scanned": int(report.files_scanned),
        "batches": int(report.batches),
        "wall_clock_ms": float(report.aggregate.get("wall_clock_ms") or 0.0),
        "model": str(provenance.get("resolved_model") or report.model or "unknown"),
        "tool_version": str(provenance.get("tool_version") or __version__),
        "git_head_sha": provenance.get("git_head_sha") or report.git.get("head_sha"),
        "usage": safe_usage,
        "benchmark": safe_benchmark,
    }


def append_history_record(
    record: dict,
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with target.open("a", encoding="utf-8", newline="") as handle:
        handle.write(line)
