import os
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
            self.assertEqual(
                result.skipped_paths_by_reason["binary_or_unknown_encoding"],
                ("blob.bin",),
            )

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

    def test_scan_enforces_max_files_while_building_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_text("a", encoding="utf-8")
            (root / "b.py").write_text("b", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "max_files"):
                scan_directory(root, ScanOptions(max_files=1))

    def test_scan_enforces_max_total_chars_while_building_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_text("a" * 4, encoding="utf-8")
            (root / "b.py").write_text("b" * 4, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "max_total_chars"):
                scan_directory(root, ScanOptions(max_total_chars=5))

    def test_ignored_directories_are_recorded_without_listing_child_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in (root / ".kinotch", root / "node_modules", root / "src" / ".venv"):
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "fixture.txt").write_text("fixture", encoding="utf-8")
            (root / "main.py").write_text("print('ok')", encoding="utf-8")

            result = scan_directory(root, ScanOptions())

        self.assertEqual(
            result.excluded_directories,
            (".kinotch", "node_modules", "src/.venv"),
        )
        self.assertNotIn(".kinotch/fixture.txt", result.skipped_paths_by_reason)
        self.assertNotIn("node_modules/fixture.txt", result.skipped_paths_by_reason)

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
            self.assertIn(".kinotch", result.excluded_directories)
            self.assertNotIn(".kinotch/fixture.txt", result.excluded_directories)

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
                if args == ("diff", "--name-only", "-z", "HEAD", "--"):
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
                if args == ("ls-files", "-co", "--exclude-standard", "-z"):
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

    def test_git_metadata_failure_does_not_fallback_to_directory_walk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".git").mkdir()
            (root / "ignored-secret.txt").write_text("private", encoding="utf-8")
            with patch("jev_audit.scanner._is_git_root", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "Git metadata"):
                    scan_directory(root, ScanOptions())

    def test_changed_gitlink_is_recorded_as_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "vendor-submodule").mkdir()

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc refs/heads/main\n", stderr="")
                if args == ("rev-parse", "--verify", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
                if args == ("diff", "--name-only", "-z", "HEAD", "--"):
                    return subprocess.CompletedProcess(args, 0, stdout="vendor-submodule\0", stderr="")
                if args == ("ls-files", "--others", "--exclude-standard", "-z"):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                if args == ("ls-files", "--stage", "-z", "--", "vendor-submodule"):
                    return subprocess.CompletedProcess(args, 0, stdout="160000 abc 0\tvendor-submodule\0", stderr="")
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ), patch(
                "jev_audit.scanner._collect_excluded_directories",
                side_effect=AssertionError("changed-only must not walk the repository"),
            ):
                result = scan_directory(root, ScanOptions(changed_only=True))

        self.assertEqual(result.files, ())
        self.assertEqual(result.skipped_counts.get("gitlink_change"), 1)
        self.assertEqual(result.skipped_paths_by_reason["gitlink_change"], ("vendor-submodule",))

    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_changed_symlink_is_recorded_as_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.txt"
            target.write_text("target", encoding="utf-8")
            link = root / "link.txt"
            try:
                os.symlink(target, link)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc refs/heads/main\n", stderr="")
                if args == ("rev-parse", "--verify", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
                if args == ("diff", "--name-only", "-z", "HEAD", "--"):
                    return subprocess.CompletedProcess(args, 0, stdout="link.txt\0", stderr="")
                if args == ("ls-files", "--others", "--exclude-standard", "-z"):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                result = scan_directory(root, ScanOptions(changed_only=True))

        self.assertEqual(result.skipped_counts.get("symlink_change"), 1)
        self.assertEqual(result.skipped_paths_by_reason["symlink_change"], ("link.txt",))

    def test_changed_regular_file_keeps_bounded_diff_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "changed.py"
            target.write_text("x=1\n", encoding="utf-8")

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc refs/heads/main\n", stderr="")
                if args == ("rev-parse", "--verify", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
                if args == ("diff", "--name-only", "-z", "HEAD", "--"):
                    return subprocess.CompletedProcess(args, 0, stdout="changed.py\0", stderr="")
                if args == ("ls-files", "--others", "--exclude-standard", "-z"):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                if args == ("ls-files", "--stage", "-z", "--", "changed.py"):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                if args == ("diff", "--no-ext-diff", "--unified=80", "HEAD", "--", "changed.py"):
                    return subprocess.CompletedProcess(
                        args,
                        0,
                        stdout="diff --git a/changed.py b/changed.py\n--- a/changed.py\n+++ b/changed.py\n@@ -1 +1 @@\n-x=0\n+x=1\n",
                        stderr="",
                    )
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                result = scan_directory(root, ScanOptions(changed_only=True))

        self.assertIn("+++ b/changed.py", result.files[0].change)
        self.assertLessEqual(len(result.files[0].change), 20_000)

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot contain newlines")
    def test_newline_git_filename_is_one_path_in_changed_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name = "line\nbreak.py"
            (root / name).write_text("x=1", encoding="utf-8")

            def fake_run_git(_root, *args):
                if args == ("symbolic-ref", "--quiet", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="refs/heads/main\n", stderr="")
                if args == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc refs/heads/main\n", stderr="")
                if args == ("rev-parse", "--verify", "HEAD"):
                    return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
                if args == ("diff", "--name-only", "-z", "HEAD", "--"):
                    return subprocess.CompletedProcess(args, 0, stdout=name + "\0", stderr="")
                if args == ("ls-files", "--others", "--exclude-standard", "-z"):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                if args == ("ls-files", "--stage", "-z", "--", name):
                    return subprocess.CompletedProcess(args, 0, stdout="100644 abc 0\t" + name + "\0", stderr="")
                if args == ("diff", "--no-ext-diff", "--unified=80", "HEAD", "--", name):
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                raise AssertionError(f"unexpected git command: {args}")

            with patch("jev_audit.scanner._is_git_root", return_value=True), patch(
                "jev_audit.scanner._run_git", side_effect=fake_run_git
            ):
                result = scan_directory(root, ScanOptions(changed_only=True))

        self.assertEqual([item.path for item in result.files], [name])

    def test_nul_git_parsers_keep_newline_filename(self):
        from jev_audit.scanner import _parse_git_nul_paths, _parse_git_stage_modes

        name = "line\nbreak.py"
        self.assertEqual(_parse_git_nul_paths(name + "\0"), [name])
        self.assertEqual(
            _parse_git_stage_modes("100644 abc 0\t" + name + "\0"),
            {name: "100644"},
        )

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot contain newlines")
    @unittest.skipUnless(shutil.which("git"), "git is required for this test")
    def test_newline_git_filename_is_one_path_in_full_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name = "line\nbreak.py"
            (root / name).write_text("x=1", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "--", name], check=True)

            result = scan_directory(root, ScanOptions())

        self.assertEqual([item.path for item in result.files], [name])

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
                if args == ("ls-files", "-co", "--exclude-standard", "-z"):
                    return subprocess.CompletedProcess(args, 0, stdout="new.py\0", stderr="")
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
