import unittest
from unittest.mock import patch

from jev_audit.auditor import _batch_state, audit_directory
from jev_audit.models import Batch, FileSnapshot


class AuditorTests(unittest.TestCase):
    def test_batch_state_only_contains_files(self):
        batch = Batch(
            index=1,
            files=(FileSnapshot(path="a.py", content="x=1", chars=3, original_chars=3, truncated=False),),
        )
        state = _batch_state(batch)
        self.assertEqual(set(state), {"files"})

    def test_invalid_limits_are_rejected_before_scan(self):
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_chars=0)
        with self.assertRaises(ValueError):
            audit_directory(".", max_file_bytes=0)
        with self.assertRaises(ValueError):
            audit_directory(".", batch_chars=0)


if __name__ == "__main__":
    unittest.main()
