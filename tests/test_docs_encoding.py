from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"


class DocumentationEncodingTests(unittest.TestCase):
    def test_markdown_docs_are_utf8_without_bom_or_known_cp932_mojibake(self) -> None:
        failures: list[str] = []
        for path in sorted(DOCS_ROOT.rglob("*.md")):
            raw = path.read_bytes()
            relative = path.relative_to(REPO_ROOT).as_posix()
            if raw.startswith(b"\xef\xbb\xbf"):
                failures.append(f"{relative}: UTF-8 BOM")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                failures.append(f"{relative}: invalid UTF-8 ({exc})")
                continue
            if "窶" in text:
                failures.append(f"{relative}: contains known CP932 mojibake marker '窶'")

        self.assertEqual([], failures, "documentation encoding failures:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
