from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jev_audit.history import (
    append_history_record,
    build_history_record,
    read_history_state,
)
from jev_audit.models import AuditReport


FIXTURE_IDS = ("clear-code", "concrete-issue", "spec-mismatch")


def report() -> AuditReport:
    return AuditReport(
        root="C:/private/repo",
        profile="development",
        files_scanned=2,
        batches=1,
        skipped_counts={},
        skipped_sensitive_paths=("secret.env",),        git={"head_sha": "a" * 40},
        batch_audits=(),
        aggregate={
            "overall": {"status": "review", "risk": 0.63},
            "usage": {
                "input_tokens": 12,
                "output_tokens": 4,
                "input_tokens_complete": True,
                "output_tokens_complete": False,
            },
            "wall_clock_ms": 42.5,
        },
        truncated_paths=("src/private.py",),
        coverage={"files_scanned": 2},
        provenance={
            "resolved_model": "jev-1.13.0",
            "tool_version": "0.2.12",
            "git_head_sha": "a" * 40,
        },
    )


class HistoryTests(unittest.TestCase):
    def test_compact_record_excludes_paths_and_source_fields(self):
        record = build_history_record(
            report(),
            surface="cli",            benchmark={
                "fixture_id": "clear-code",
                "score": 100,
                "error": None,
                "recent_scores": [100],
                "recent_mean": 100.0,
            },
            timestamp="2026-09-27T00:00:00Z",
        )
        serialized = json.dumps(record, ensure_ascii=False)
        self.assertEqual(record["surface"], "cli")
        self.assertEqual(record["status"], "review")
        self.assertEqual(record["risk"], 0.63)
        self.assertEqual(record["git_head_sha"], "a" * 40)
        self.assertNotIn("root", record)
        self.assertNotIn("paths", serialized)
        self.assertNotIn("private.py", serialized)
        self.assertNotIn("secret.env", serialized)

    def test_history_state_ignores_malformed_lines_and_caps_scores_at_ten(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            rows = [{"benchmark": {"fixture_id": FIXTURE_IDS[i % 3], "score": 100 if i % 2 else None}} for i in range(12)]
            path.write_text("bad json\n" + "\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            state = read_history_state(path, FIXTURE_IDS)
            self.assertEqual(state.next_fixture_index, 0)
            self.assertEqual(len(state.recent_scores), 10)
            self.assertEqual(state.recent_scores[-1], 100)

    def test_append_writes_exactly_one_jsonl_record(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "history.jsonl"
            append_history_record({"schema_version": 1, "status": "clear"}, path)
            raw = path.read_text(encoding="utf-8")
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(len(raw.splitlines()), 1)
            self.assertEqual(json.loads(raw)["status"], "clear")


if __name__ == "__main__":
    unittest.main()
