import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from jev_audit import cli


class CLITests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
