import unittest

from jev_audit.profiles import available_profiles, load_profile


class ProfileTests(unittest.TestCase):
    def test_bundled_profiles_load(self):
        names = available_profiles()
        self.assertIn("development", names)
        self.assertIn("generic", names)
        profile = load_profile("development")
        self.assertGreaterEqual(len(profile.rules), 5)
        self.assertIn("clear", profile.status_criteria)


if __name__ == "__main__":
    unittest.main()
