import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from jev_audit.auditor import _batch_state, audit_directory
from jev_audit.models import (
    AuditProfile,
    AuditRule,
    Batch,
    BatchAudit,
    FileSnapshot,
    JevResult,
    ScanResult,
)
from jev_audit.jev_gateway import estimate_question_overhead


class AuditorTests(unittest.TestCase):
    def test_batch_state_only_contains_files(self):
        batch = Batch(
            index=1,
            files=(FileSnapshot(path="a.py", content="x=1", chars=3, original_chars=3, truncated=False),),
        )
        state = _batch_state(batch)
        self.assertEqual(set(state), {"files"})

    def test_batch_state_includes_changed_hunk_when_available(self):
        batch = Batch(
            index=1,
            files=(
                FileSnapshot(
                    path="a.py",
                    content="x=2",
                    chars=3,
                    original_chars=3,
                    truncated=False,
                    change="@@ -1 +1 @@\n-x=1\n+x=2\n",
                ),
            ),
        )
        self.assertEqual(_batch_state(batch)["files"][0]["change"], batch.files[0].change)

    def test_invalid_limits_are_rejected_before_scan(self):
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_chars=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_bytes=0)
        with self.assertRaises(ValueError):
            audit_directory(".", batch_chars=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_files=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_total_chars=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_batches=0)
        with self.assertRaises(ValueError):
            audit_directory(".", workers=0)

    def test_total_guardrails_reject_before_any_jev_request(self):
        files = tuple(
            FileSnapshot(
                path=f"file-{index}.py",
                content="x" * 100,
                chars=100,
                original_chars=100,
                truncated=False,
            )
            for index in range(2)
        )
        fake_scan = ScanResult(
            root="C:/repo",
            files=files,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor._audit_one"
        ) as audit_one:
            with self.assertRaisesRegex(ValueError, "max_total_chars"):
                audit_directory(".", max_total_chars=150)
        audit_one.assert_not_called()

    def test_total_guardrail_includes_question_overhead_for_each_batch(self):
        files = tuple(
            FileSnapshot(
                path=f"file-{index}.py",
                content="x" * 10,
                chars=10,
                original_chars=10,
                truncated=False,
            )
            for index in range(2)
        )
        fake_scan = ScanResult(
            root="C:/repo",
            files=files,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        profile = AuditProfile(
            name="custom",
            description="",
            rules=(AuditRule(id="R1", title="Rule", description="x" * 1000),),
            status_criteria={
                "clear": "ok",
                "review": "review",
                "rework": "rework",
                "unknown": "unknown",
            },
        )
        overhead = estimate_question_overhead(profile)
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor.load_profile", return_value=profile
        ), patch("jev_audit.auditor._audit_one") as audit_one:
            with self.assertRaisesRegex(ValueError, "max_total_chars"):
                audit_directory(
                    ".",
                    batch_chars=64,
                    max_total_chars=20 + (overhead * 2) - 1,
                )
        audit_one.assert_not_called()

    def test_file_and_batch_guardrails_reject_before_any_jev_request(self):
        files = tuple(
            FileSnapshot(
                path=f"file-{index}.py",
                content="x" * 10,
                chars=10,
                original_chars=10,
                truncated=False,
            )
            for index in range(3)
        )
        fake_scan = ScanResult(
            root="C:/repo",
            files=files,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        for kwargs, message in (
            ({"max_files": 2}, "max_files"),
            ({"max_batches": 1, "batch_chars": 100}, "max_batches"),
        ):
            with self.subTest(message=message), patch(
                "jev_audit.auditor.scan_directory", return_value=fake_scan
            ), patch("jev_audit.auditor._audit_one") as audit_one:
                with self.assertRaisesRegex(ValueError, message):
                    audit_directory(".", **kwargs)
                audit_one.assert_not_called()

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
        self.assertEqual(report.provenance["requested_workers"], 4)
        self.assertEqual(report.provenance["effective_workers"], 0)
        self.assertEqual(json.loads(json.dumps(report.to_dict()))["provenance"]["effective_workers"], 0)
        audit_one.assert_not_called()

    def test_changed_only_with_only_skipped_files_returns_unknown_report(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(),
            skipped_counts={"sensitive": 1},
            skipped_sensitive_paths=(".env",),
            git={"is_git_repo": True, "deleted_paths": ()},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan):
            report = audit_directory(".", changed_only=True)

        self.assertEqual(report.status, "unknown")
        self.assertEqual(report.files_scanned, 0)
        self.assertEqual(report.batches, 0)
        self.assertEqual(report.skipped_counts, {"sensitive": 1})

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

    def test_batch_failure_stops_submitting_after_inflight_window(self):
        files = tuple(
            FileSnapshot(
                path=f"file-{index}.py",
                content="x" * 100,
                chars=100,
                original_chars=100,
                truncated=False,
            )
            for index in range(1, 6)
        )
        fake_scan = ScanResult(
            root="C:/repo",
            files=files,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        started: list[int] = []
        release = threading.Event()

        def fake_audit_one(batch, _profile, _model):
            started.append(batch.index)
            if batch.index == 1:
                release.set()
                raise RuntimeError("provider failed")
            release.wait(1.0)
            return BatchAudit(
                index=batch.index,
                paths=tuple(batch.paths),
                chars=batch.chars,
                result=JevResult(
                    model="jev-test",
                    elapsed_ms=1.0,
                    usage={"input_tokens": 1, "output_tokens": 1},
                    choices={
                        "local_status": {
                            "choice": "clear",
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
                ),
            )

        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor._audit_one", side_effect=fake_audit_one
        ):
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                audit_directory(".", batch_chars=160, workers=2)

        self.assertLessEqual(len(started), 2)

    def test_report_preserves_coverage_and_provenance(self):
        files = (
            FileSnapshot(
                path="truncated.py",
                content="short",
                chars=5,
                original_chars=10,
                truncated=True,
            ),
            FileSnapshot(
                path="full.py",
                content="full",
                chars=4,
                original_chars=4,
                truncated=False,
            ),
        )
        fake_scan = ScanResult(
            root="C:/repo",
            files=files,
            skipped_counts={"binary_or_unknown_encoding": 1},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": (), "head_sha": "abc123"},
            skipped_paths_by_reason={"binary_or_unknown_encoding": ("blob.bin",)},
            excluded_directories=(".kinotch",),
        )
        result = JevResult(
            model="jev-custom",
            elapsed_ms=1.0,
            usage={"input_tokens": 1, "output_tokens": 1},
            choices={
                "local_status": {
                    "probabilities": {
                        "clear": 1.0,
                        "review": 0.0,
                        "rework": 0.0,
                        "unknown": 0.0,
                    }
                }
            },
            nouls={"concrete_issue": 0.0, "spec_mismatch": 0.0, "regression_risk": 0.0},
        )
        batch_audit = BatchAudit(index=1, paths=("truncated.py", "full.py"), chars=9, result=result)
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor._audit_one", return_value=batch_audit
        ):
            report = audit_directory(".", model="jev-custom", workers=1)

        self.assertEqual(report.truncated_paths, ("truncated.py",))
        self.assertEqual(report.skipped_paths_by_reason["binary_or_unknown_encoding"], ("blob.bin",))
        self.assertEqual(report.coverage["sent_chars"], 9)
        self.assertEqual(report.coverage["original_chars"], 14)
        self.assertEqual(report.coverage["files_skipped"], 1)
        self.assertEqual(report.excluded_directories, (".kinotch",))
        self.assertEqual(report.coverage["excluded_directory_count"], 1)
        self.assertEqual(report.provenance["requested_model"], "jev-custom")
        self.assertEqual(report.provenance["resolved_model"], "jev-custom")
        self.assertEqual(report.provenance["requested_workers"], 1)
        self.assertEqual(report.provenance["effective_workers"], 1)
        self.assertEqual(report.provenance["batch_count"], 1)
        self.assertGreater(report.provenance["question_overhead_chars_per_batch"], 0)
        self.assertGreater(report.provenance["estimated_total_input_chars"], 0)
        self.assertEqual(report.provenance["git_head_sha"], "abc123")
        self.assertTrue(report.provenance["profile_sha256"])

    def test_provenance_clamps_effective_workers_to_batch_count(self):
        fake_scan = ScanResult(
            root="C:/repo",
            files=(FileSnapshot(path="a.py", content="x", chars=1, original_chars=1, truncated=False),),
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": False, "deleted_paths": ()},
        )
        result = JevResult(
            model="jev-test",
            elapsed_ms=1.0,
            usage={"input_tokens": 1, "output_tokens": 1},
            choices={"local_status": {"probabilities": {"clear": 1.0, "review": 0.0, "rework": 0.0, "unknown": 0.0}}},
            nouls={"concrete_issue": 0.0, "spec_mismatch": 0.0, "regression_risk": 0.0},
        )
        with patch("jev_audit.auditor.scan_directory", return_value=fake_scan), patch(
            "jev_audit.auditor._audit_one",
            return_value=BatchAudit(index=1, paths=("a.py",), chars=1, result=result),
        ):
            report = audit_directory(".", workers=16)

        self.assertEqual(report.provenance["requested_workers"], 16)
        self.assertEqual(report.provenance["effective_workers"], 1)
        self.assertEqual(report.provenance["workers"], 1)


if __name__ == "__main__":
    unittest.main()
