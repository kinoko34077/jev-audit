import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jev_audit.auditor import _batch_state, audit_directory
from jev_audit.models import Batch, FileSnapshot, JevResult, ScanResult


class AuditorTests(unittest.TestCase):
    def test_batch_state_only_contains_files(self):
        batch = Batch(
            index=1,
            files=(FileSnapshot(path="a.py", content="x=1", chars=3, original_chars=3, truncated=False),),
        )
        state = _batch_state(batch)
        self.assertEqual(set(state), {"files"})

    def test_invalid_limits_are_rejected_before_scan(self):
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_chars=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_bytes=0)
        with self.assertRaises(ValueError):
            audit_directory(".", batch_chars=0)

    def test_wall_clock_is_measured_separately_from_batch_api_work(self):
        fake_result = JevResult(
            model="jev-test",
            elapsed_ms=80.0,
            usage={"input_tokens": 10, "output_tokens": 4},
            choices={
                "local_status": {
                    "choice": "clear",
                    "confidence": 1.0,
                    "probabilities": {
                        "clear": 1.0,
                        "review": 0.0,
                        "rework": 0.0,
                        "unknown": 0.0,
                    },
                }
            },
            nouls={
                "concrete_issue": 0.0,
                "spec_mismatch": 0.0,
                "regression_risk": 0.0,
            },
        )
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "a.py").write_text("x=1", encoding="utf-8")
            with patch("jev_audit.auditor.audit_with_jev", return_value=fake_result), patch(
                "jev_audit.auditor.time.perf_counter", side_effect=[10.0, 10.25]
            ):
                report = audit_directory(temp, workers=1)

        self.assertAlmostEqual(report.aggregate["wall_clock_ms"], 250.0)
        self.assertAlmostEqual(report.aggregate["total_batch_latency_ms"], 80.0)

    def test_deletion_only_changed_set_returns_unknown_report(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(),
            skipped_counts={"deleted_change_without_content": 1},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": ("deleted.py",)},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan):
            report = audit_directory(".", changed_only=True)
        self.assertEqual(report.status, "unknown")
        self.assertEqual(report.files_scanned, 0)
        self.assertEqual(report.batches, 0)
        self.assertEqual(report.git["deleted_paths"], ("deleted.py",))

    def test_clean_changed_only_returns_clear_noop_without_calling_jev(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(),
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": ()},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor._audit_one"
        ) as audit_one:
            report = audit_directory(".", changed_only=True)

        self.assertEqual(report.status, "clear")
        self.assertEqual(report.files_scanned, 0)
        self.assertEqual(report.batches, 0)
        audit_one.assert_not_called()

    def test_changed_only_with_only_skipped_files_is_not_a_clean_noop(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(),
            skipped_counts={"sensitive": 1},
            skipped_sensitive_paths=(".env",),
            git={"is_git_repo": True, "deleted_paths": ()},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan):
            with self.assertRaisesRegex(RuntimeError, "No auditable text files"):
                audit_directory(".", changed_only=True)

    def test_model_is_forwarded_to_each_batch(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(
                FileSnapshot(
                    path="a.py", content="x=1", chars=3, original_chars=3, truncated=False
                ),
            ),
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        fake_result = JevResult(
            model="jev-1.13.0",
            elapsed_ms=1.0,
            usage={"input_tokens": 1, "output_tokens": 1},
            choices={"local_status": {"probabilities": {"clear": 1.0}}},
            nouls={"concrete_issue": 0.0, "spec_mismatch": 0.0, "regression_risk": 0.0},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor.audit_with_jev", return_value=fake_result
        ) as gateway:
            audit_directory(".", workers=1, model="jev-custom")

        self.assertEqual(gateway.call_args.kwargs["model"], "jev-custom")


if __name__ == "__main__":
    unittest.main()
