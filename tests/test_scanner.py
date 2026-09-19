import tempfile
import unittest
from pathlib import Path

from jev_audit.scanner import ScanOptions, scan_directory


class ScannerTests(unittest.TestCase):
    def test_sensitive_and_binary_are_not_uploaded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
            (root / "blob.bin").write_bytes(b"abc\x00def")

            result = scan_directory(root, ScanOptions())
            paths = {item.path for item in result.files}
            self.assertIn("main.py", paths)
            self.assertNotIn(".env", paths)
            self.assertNotIn("blob.bin", paths)
            self.assertIn(".env", result.skipped_sensitive_paths)


if __name__ == "__main__":
    unittest.main()
