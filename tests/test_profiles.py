import json
import tempfile
import unittest
from pathlib import Path

from jev_audit.profiles import available_profiles, load_profile


class ProfileTests(unittest.TestCase):
    def test_bundled_profiles_load(self):
        names = available_profiles()
        self.assertIn("development", names)
        self.assertIn("generic", names)
        profile = load_profile("development")
        self.assertGreaterEqual(len(profile.rules), 5)
        self.assertIn("clear", profile.status_criteria)

    def test_custom_profile_rejects_unknown_status_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text(json.dumps({
                "name": "bad",
                "status_criteria": {"ok": "ok", "bad": "bad"},
                "rules": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(str(path))


if __name__ == "__main__":
    unittest.main()
