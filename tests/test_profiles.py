import json
import os
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

    def test_bundled_name_cannot_be_shadowed_by_working_directory_file(self):
        with tempfile.TemporaryDirectory() as temp:
            shadow = Path(temp) / "development"
            shadow.write_text(
                json.dumps(
                    {
                        "name": "shadow",
                        "status_criteria": {
                            "clear": "ok",
                            "review": "review",
                            "rework": "rework",
                            "unknown": "unknown",
                        },
                        "rules": [],
                    }
                ),
                encoding="utf-8",
            )
            old = Path.cwd()
            try:
                os.chdir(temp)
                profile = load_profile("development")
            finally:
                os.chdir(old)

        self.assertEqual(profile.name, "development")

    def test_custom_profile_directory_is_rejected_as_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "JSON file"):
                load_profile(temp)

    def test_profile_schema_errors_are_normalized_to_value_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text(json.dumps({"name": "bad", "rules": [{}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(str(path))


if __name__ == "__main__":
    unittest.main()
