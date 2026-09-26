import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from jev_audit import cli
from jev_audit.runtime_bridge import RuntimeDependencyError


class CLITests(unittest.TestCase):
    def test_guardrail_options_are_forwarded(self):
        with patch.object(cli, "run_audit", return_value=type("Report", (), {"status": "clear"})()) as run_audit, patch.object(
            cli, "format_report", return_value="clear"
        ), redirect_stdout(io.StringIO()) as output:
            exit_code = cli.main(
                [
                    ".",
                    "--max-files",
                    "12",
                    "--max-total-chars",
                    "3456",
                    "--max-batches",
                    "7",
                ]
            )

        self.assertEqual(exit_code, 0)
        run_audit.assert_called_once()
        kwargs = run_audit.call_args.kwargs
        self.assertEqual(kwargs["max_files"], 12)
        self.assertEqual(kwargs["max_total_chars"], 3456)
        self.assertEqual(kwargs["max_batches"], 7)

    def test_clean_changed_only_can_complete_without_api_key(self):
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), patch.object(
            cli, "run_audit", return_value=type("Report", (), {"status": "clear"})()
        ) as run_audit, patch.object(cli, "format_report", return_value="clear"), redirect_stdout(output):
            exit_code = cli.main([".", "--changed-only"])

        self.assertEqual(exit_code, 0)
        run_audit.assert_called_once()
        self.assertEqual(output.getvalue(), "clear\n")

    def test_save_failure_is_reported_without_traceback(self):
        error_output = io.StringIO()
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}, clear=True), patch.object(
            cli, "run_audit", return_value=object()
        ), patch.object(cli, "write_json", side_effect=OSError("disk full")), redirect_stderr(error_output):
            exit_code = cli.main([".", "--save", "result.json"])

        self.assertEqual(exit_code, 2)
        self.assertIn("ERROR: could not save report: disk full", error_output.getvalue())
        self.assertNotIn("Traceback", error_output.getvalue())

    def test_runtime_dependency_failure_is_explicit_exit_two(self):
        error_output = io.StringIO()
        with patch.object(
            cli,
            "run_audit",
            side_effect=RuntimeDependencyError("kinotch-runtime missing"),
        ), redirect_stderr(error_output):
            exit_code = cli.main(["."])

        self.assertEqual(exit_code, 2)
        self.assertIn("DEPENDENCY_ERROR", error_output.getvalue())


    def test_base_ref_is_forwarded_with_changed_only(self):
        report = type("Report", (), {"status": "clear"})()
        with patch.object(cli, "run_audit", return_value=report) as run_audit, patch.object(
            cli, "format_report", return_value="clear"
        ), redirect_stdout(io.StringIO()):
            exit_code = cli.main([".", "--changed-only", "--base-ref", "base123"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(run_audit.call_args.kwargs["changed_only"])
        self.assertEqual(run_audit.call_args.kwargs["base_ref"], "base123")

    def test_base_ref_without_changed_only_uses_existing_invalid_input_exit(self):
        error_output = io.StringIO()
        with patch.object(
            cli, "run_audit", side_effect=ValueError("base_ref requires changed_only=True")
        ), redirect_stderr(error_output):
            exit_code = cli.main([".", "--base-ref", "base123"])
        self.assertEqual(exit_code, 2)
        self.assertIn("base_ref requires changed_only=True", error_output.getvalue())

if __name__ == "__main__":
    unittest.main()
