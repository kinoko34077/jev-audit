from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jev_audit.benchmark import BenchmarkObservation
from jev_audit.models import AuditReport
from jev_audit.observability import record_completed_audit


def report(*, batches=1) -> AuditReport:
    return AuditReport(
        root="C:/private/repo",
        profile="development",
        files_scanned=1 if batches else 0,
        batches=batches,
        skipped_counts={},
        skipped_sensitive_paths=(),
        git={"head_sha": "a" * 40},
        batch_audits=(),
        aggregate={
            "overall": {"status": "clear", "risk": 0.1},
            "usage": {"input_tokens": 10 if batches else None, "output_tokens": 3 if batches else None,
                      "input_tokens_complete": True, "output_tokens_complete": True},
            "wall_clock_ms": 5.0,
        },
        provenance={"resolved_model": "jev-1.13.0", "tool_version": "0.2.12", "git_head_sha": "a" * 40},
    )

class ObservabilityTests(unittest.TestCase):
    def test_provider_backed_audit_runs_one_fixture_and_appends_rolling_record(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            calls = []
            def fake_runner(index, model):
                calls.append((index, model))
                return BenchmarkObservation("clear-code", 100, None)
            record = record_completed_audit(
                report(), surface="cli", history_path=path,
                benchmark_runner=fake_runner, timestamp="2026-09-27T00:00:00Z",
            )
            self.assertEqual(calls, [(0, "jev-1.13.0")])
            self.assertEqual(record["benchmark"]["recent_scores"], [100])
            self.assertEqual(record["benchmark"]["recent_mean"], 100.0)
            self.assertEqual(record["benchmark"]["next_fixture_id"], "concrete-issue")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["surface"], "cli")

    def test_clean_noop_is_provider_free_and_preserves_prior_window(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            path.write_text(json.dumps({"benchmark": {"fixture_id": "clear-code", "score": 100}}) + "\n", encoding="utf-8")
            def must_not_run(*args, **kwargs):
                raise AssertionError("benchmark provider call must not run")
            record = record_completed_audit(
                report(batches=0), surface="local_mcp", history_path=path,
                benchmark_runner=must_not_run,
            )
            self.assertIsNone(record["benchmark"]["fixture_id"])
            self.assertIsNone(record["benchmark"]["score"])
            self.assertEqual(record["benchmark"]["next_fixture_id"], "concrete-issue")
            self.assertEqual(record["benchmark"]["recent_scores"], [100])
            self.assertEqual(record["surface"], "local_mcp")

    def test_history_write_failure_never_changes_real_audit_result(self):
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            path = blocker / "history.jsonl"
            record = record_completed_audit(
                report(), surface="cli", history_path=path,
                benchmark_runner=lambda index, model: BenchmarkObservation("clear-code", 100, None),
            )
            self.assertIsNone(record)


if __name__ == "__main__":
    unittest.main()
