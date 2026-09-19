import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jev_audit import jev_gateway
from jev_audit.models import AuditProfile, AuditRule


class FakeChoice:
    def __init__(self, *, instructions=None, criteria=None):
        self.instructions = instructions
        self.criteria = criteria


class FakeNoul:
    def __init__(self, *, instructions=None, criteria=None):
        self.instructions = instructions
        self.criteria = criteria


class GatewayTests(unittest.TestCase):
    def test_questions_are_minimal_and_rules_feed_local_status(self):
        profile = AuditProfile(
            name="test",
            description="",
            rules=(AuditRule(id="R1", title="Rule 1", description="Check one"),),
            status_criteria={
                "clear": "ok",
                "review": "review",
                "rework": "rework",
                "unknown": "unknown",
            },
        )
        with patch.object(jev_gateway, "_sdk", return_value=(FakeChoice, FakeNoul, object)):
            questions = jev_gateway._build_questions(profile)

        self.assertEqual(
            set(questions),
            {"local_status", "concrete_issue", "spec_mismatch", "regression_risk"},
        )
        self.assertIn("R1", questions["local_status"].instructions)
        self.assertIn("監査対象データ", questions["local_status"].instructions)

    def test_partial_jev_response_is_rejected(self):
        response = SimpleNamespace(
            choices={
                "local_status": SimpleNamespace(
                    choice="clear", confidence=1.0, probabilities={"clear": 1.0}
                )
            },
            nouls={},
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            model="jev-test",
        )
        with self.assertRaises(RuntimeError):
            jev_gateway._serialize_response(response, 1.0)


if __name__ == "__main__":
    unittest.main()
