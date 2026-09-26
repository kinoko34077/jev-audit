import unittest

from jev_audit.batching import fit_files_to_batch_limit, make_batches
from jev_audit.models import FileSnapshot


class BatchingTests(unittest.TestCase):
    def test_batches_preserve_files(self):
        files = tuple(
            FileSnapshot(
                path=f"f{i}.txt",
                content="x" * 20,
                chars=20,
                original_chars=20,
                truncated=False,
            )
            for i in range(5)
        )
        batches = make_batches(files, max_chars=70)
        flattened = [path for batch in batches for path in batch.paths]
        self.assertEqual(flattened, [f"f{i}.txt" for i in range(5)])
        self.assertGreater(len(batches), 1)

    def test_single_item_cannot_exceed_batch_limit(self):
        item = FileSnapshot(
            path="large.py",
            content="x" * 100,
            chars=100,
            original_chars=100,
            truncated=False,
        )
        with self.assertRaisesRegex(ValueError, "exceeds max_chars"):
            make_batches((item,), max_chars=100)

    def test_changed_hunk_counts_toward_batch_limit(self):
        item = FileSnapshot(
            path="changed.py",
            content="x",
            chars=1,
            original_chars=1,
            truncated=False,
            change="diff" * 20,
        )
        with self.assertRaisesRegex(ValueError, "exceeds max_chars"):
            make_batches((item,), max_chars=50)

    def test_changed_hunk_can_be_trimmed_to_fit_batch_limit(self):
        item = FileSnapshot(
            path="changed.py",
            content="x" * 12_000,
            chars=12_000,
            original_chars=12_000,
            truncated=False,
            change="d" * 20_000,
        )
        fitted = fit_files_to_batch_limit((item,), max_chars=32_000)
        self.assertEqual(len(fitted), 1)
        self.assertEqual(fitted[0].content, item.content)
        self.assertLess(len(fitted[0].change), len(item.change))
        self.assertLessEqual(
            fitted[0].chars + len(fitted[0].change) + len(fitted[0].path) + 32,
            32_000,
        )
        self.assertEqual(len(make_batches(fitted, max_chars=32_000)), 1)

    def test_changed_hunk_fit_still_rejects_content_that_cannot_fit(self):
        item = FileSnapshot(
            path="large.py",
            content="x" * 100,
            chars=100,
            original_chars=100,
            truncated=False,
            change="diff",
        )
        with self.assertRaisesRegex(ValueError, "exceeds max_chars"):
            fit_files_to_batch_limit((item,), max_chars=100)


if __name__ == "__main__":
    unittest.main()
