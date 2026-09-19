import unittest

from jev_audit.batching import make_batches
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


if __name__ == "__main__":
    unittest.main()
