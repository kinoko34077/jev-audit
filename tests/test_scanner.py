import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jev_audit.scanner import ScanOptions, scan_directory


class ScannerTests(unittest.TestCase):
    def test_sensitive_and_binary_are_not_uploaded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
            (root / "private.pem").write_text("-----BEGIN PRIVATE KEY-----\nsecret", encoding="utf-8")
            (root / "blob.bin").write_bytes(b"abc\x00def")

            result = scan_directory(root, ScanOptions())
            paths = {item.path for item in result.files}
            self.assertIn("main.py", paths)
            self.assertNotIn(".env", paths)
            self.assertNotIn("private.pem", paths)
            self.assertNotIn("blob.bin", paths)
            self.assertIn(".env", result.skipped_sensitive_paths)
            self.assertIn("private.pem", result.skipped_sensitive_paths)

    def test_audit_directory_is_ignored_as_generated_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".audit").mkdir()
            (root / ".audit" / "result.json").write_text("{}", encoding="utf-8")
            (root / "main.py").write_text("print('ok')", encoding="utf-8")

            result = scan_directory(root, ScanOptions())
            paths = {item.path for item in result.files}
            self.assertIn("main.py", paths)
            self.assertNotIn(".audit/result.json", paths)

    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_kinotch_directory_is_ignored_from_repository_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".kinotch").mkdir()
            (root / ".kinotch" / "fixture.txt").write_text("invalid fixture", encoding="utf-8")
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", ".kinotch/fixture.txt", "main.py"], check=True)

            result = scan_directory(root, ScanOptions())
            paths = {item.path for item in result.files}
            self.assertIn("main.py", paths)
            self.assertNotIn(".kinotch/fixture.txt", paths)

    def test_missing_git_falls_back_to_directory_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            with patch("jev_audit.scanner.shutil.which", return_value=None):
                result = scan_directory(root, ScanOptions())
            self.assertFalse(result.git["is_git_repo"])
            self.assertEqual([item.path for item in result.files], ["main.py"])

    def test_changed_only_without_git_is_rejected_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            with patch("jev_audit.scanner.shutil.which", return_value=None):
                with self.assertRaises(ValueError):
                    scan_directory(root, ScanOptions(changed_only=True))

    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_git_repo_keeps_non_ascii_file_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            target = root / "日本語.md"
            target.write_text("監査対象", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "日本語.md"], check=True)

            result = scan_directory(root, ScanOptions())
            paths = {item.path for item in result.files}
            self.assertIn("日本語.md", paths)

    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_changed_only_handles_repo_without_head(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            target = root / "staged.py"
            target.write_text("x=1", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "staged.py"], check=True)

            result = scan_directory(root, ScanOptions(changed_only=True))
            paths = {item.path for item in result.files}
            self.assertIn("staged.py", paths)

    def test_changed_only_does_not_fallback_on_non_head_git_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc123 refs/heads/main\n", stderr="")
                if args == ("diff", "--name-only", "HEAD", "--"):
                    return subprocess.CompletedProcess(
                        args,
                        128,
                        stdout="",
                        stderr="fatal: simulated diff failure",
                    )
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated diff failure"):
                    scan_directory(root, ScanOptions(changed_only=True))

    def test_full_scan_does_not_hide_git_ls_files_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fake_run_git(_root, *args):
                if args == ("ls-files", "-co", "--exclude-standard"):
                    return subprocess.CompletedProcess(
                        args,
                        128,
                        stdout="",
                        stderr="fatal: simulated ls-files failure",
                    )
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated ls-files failure"):
                    scan_directory(root, ScanOptions())

    def test_changed_only_unborn_head_uses_ref_state_not_error_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "new.py").write_text("x=1", encoding="utf-8")

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(
                        args,
                        1,
                        stdout="",
                        stderr="fatal: révision introuvable",
                    )
                if args == ("ls-files", "-co", "--exclude-standard"):
                    return subprocess.CompletedProcess(args, 0, stdout="new.py\n", stderr="")
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                result = scan_directory(root, ScanOptions(changed_only=True))

            self.assertEqual([item.path for item in result.files], ["new.py"])

    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_changed_only_reports_deleted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            target = root / "deleted.py"
            target.write_text("x=1", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "deleted.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True)
            target.unlink()

            result = scan_directory(root, ScanOptions(changed_only=True))
            self.assertEqual(result.files, ())
            self.assertEqual(result.skipped_counts.get("deleted_change_without_content"), 1)
            self.assertEqual(result.git.get("deleted_paths"), ("deleted.py",))


if __name__ == "__main__":
    unittest.main()
