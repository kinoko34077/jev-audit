from __future__ import annotations

from pathlib import Path
from typing import Callable

from .benchmark import BenchmarkObservation, fixture_ids, run_benchmark
from .history import (
    DEFAULT_HISTORY_PATH,
    append_history_record,
    build_history_record,
    read_history_state,
    rolling_mean,
)
from .models import AuditReport


def record_completed_audit(
    report: AuditReport,
    *,
    surface: str,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    benchmark_runner: Callable[[int, str], BenchmarkObservation] = run_benchmark,
    timestamp: str | None = None,
) -> dict | None:
    try:
        ids = fixture_ids()
        state = read_history_state(history_path, ids)
        recent = list(state.recent_scores)
        next_fixture_index = state.next_fixture_index
        if report.batches > 0:
            model = str(report.provenance.get("resolved_model") or report.model)
            observation = benchmark_runner(next_fixture_index, model)
            recent.append(observation.score)
            recent = recent[-10:]
            next_fixture_index = (next_fixture_index + 1) % len(ids) if ids else 0
            benchmark = {
                "fixture_id": observation.fixture_id,
                "next_fixture_id": ids[next_fixture_index] if ids else None,
                "score": observation.score,
                "error": observation.error,
                "recent_scores": recent,
                "recent_mean": rolling_mean(recent),
            }
        else:
            benchmark = {
                "fixture_id": None,
                "next_fixture_id": ids[next_fixture_index] if ids else None,
                "score": None,
                "error": None,
                "recent_scores": recent,
                "recent_mean": rolling_mean(recent),
            }
        record = build_history_record(
            report,
            surface=surface,
            benchmark=benchmark,
            timestamp=timestamp,
        )
        append_history_record(record, history_path)
        return record
    except Exception:
        return None
