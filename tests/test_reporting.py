import unittest

from jev_audit.models import AuditReport, BatchAudit, JevResult
from jev_audit.reporting import format_report


class ReportingTests(unittest.TestCase):
    def test_report_marks_unreported_token_usage(self):
        report = AuditReport(
            root="C:/repo",
            profile="development",
            files_scanned=0,
            batches=0,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": ()},
            batch_audits=(),
            aggregate={
                "overall": {"status": "unknown"},
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "input_tokens_complete": False,
                    "output_tokens_complete": True,
                    "input_tokens_missing_batches": 2,
                    "output_tokens_missing_batches": 0,
                },
            },
        )
        text = format_report(report)
        self.assertIn("tokens : input=12+ [2 batches unreported] output=4", text)

    def test_report_exposes_driver_rework_unknown_and_wall_clock(self):
        result = JevResult(
            model="jev-test",
            elapsed_ms=80.0,
            usage={"input_tokens": 10, "output_tokens": 4},
            choices={
                "local_status": {
                    "choice": "review",
                    "confidence": 0.8,
                    "probabilities": {
                        "clear": 0.1,
                        "review": 0.5,
                        "rework": 0.2,
                        "unknown": 0.2,
                    },
                }
            },
            nouls={
                "concrete_issue": 0.57,
                "spec_mismatch": 0.83,
                "regression_risk": 0.60,
            },
        )
        batch = BatchAudit(index=1, paths=("a.py",), chars=10, result=result)
        aggregate = {
            "overall": {
                "status": "review",
                "risk": 0.83,
                "status_trigger": {
                    "kind": "concrete_risk",
                    "batch_index": 1,
                    "value": 0.83,
                    "risk_driver": "spec_mismatch",
                    "paths": ["a.py"],
                },
            },
            "signals": {
                "concrete_issue": {"max": 0.57, "mean": 0.57},
                "spec_mismatch": {"max": 0.83, "mean": 0.83},
                "regression_risk": {"max": 0.60, "mean": 0.60},
            },
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "wall_clock_ms": 123.4,
            "total_batch_latency_ms": 80.0,
            "highest_risk_batches": [
                {
                    "index": 1,
                    "risk": 0.83,
                    "risk_driver": "spec_mismatch",
                    "concrete_issue": 0.57,
                    "rework_probability": 0.20,
                    "actionable_probability": 0.70,
                    "unknown_probability": 0.20,
                    "paths": ["a.py"],
                }
            ],
        }
        report = AuditReport(
            root="C:/repo",
            profile="development",
            files_scanned=1,
            batches=1,
            skipped_counts={},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": ("old.py",)},
            batch_audits=(batch,),
            aggregate=aggregate,
        )

        text = format_report(report)
        self.assertIn("reason : risk= 83.0% via=spec_mismatch at batch #1", text)
        self.assertIn("trigger paths: a.py", text)
        self.assertIn("elapsed: 123.4 ms (wall-clock)", text)
        self.assertIn("api work: 80.0 ms", text)
        self.assertIn("via=spec_mismatch", text)
        self.assertIn("rework= 20.0%", text)
        self.assertIn("unknown= 20.0%", text)
        self.assertIn("deleted file contents were not available to audit", text)

    def test_report_displays_coverage_and_provenance_summary(self):
        report = AuditReport(
            root="C:/repo",
            profile="development",
            files_scanned=1,
            batches=1,
            skipped_counts={"binary_or_unknown_encoding": 1},
            skipped_sensitive_paths=(),
            git={"is_git_repo": True, "deleted_paths": ()},
            batch_audits=(),
            aggregate={"overall": {"status": "unknown"}},
            truncated_paths=("large.py",),
            coverage={
                "sent_chars": 50,
                "original_chars": 100,
                "char_coverage": 0.5,
                "files_truncated": 1,
                "files_skipped": 1,
                "file_entries_skipped": 1,
                "excluded_directory_count": 2,
            },
            excluded_directories=(".kinotch", "src/.venv"),
            provenance={
                "tool_version": "0.2.10",
                "resolved_model": "jev-1.13.0",
                "git_head_sha": "abc123",
            },
        )

        text = format_report(report)
        self.assertIn("coverage: scanned chars=50/100 (50.0%)", text)
        self.assertIn("truncated=1", text)
        self.assertIn("file_entries_skipped=1", text)
        self.assertIn("directories_excluded=2", text)
        self.assertIn("excluded directories: .kinotch, src/.venv", text)
        self.assertIn("provenance: tool=0.2.10 model=jev-1.13.0 git=abc123", text)


if __name__ == "__main__":
    unittest.main()
