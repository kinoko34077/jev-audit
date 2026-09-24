import math
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
    def test_model_resolution_is_pinned_and_explicitly_overridable(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(jev_gateway._resolve_model(None), "jev-1.13.0")
        with patch.dict("os.environ", {"TYPESAFE_DEFAULT_MODEL": "jev-1.14.0"}, clear=True):
            self.assertEqual(jev_gateway._resolve_model(None), "jev-1.14.0")
        self.assertEqual(jev_gateway._resolve_model("jev-custom"), "jev-custom")

    def test_audit_with_jev_passes_resolved_model_to_sdk(self):
        captured = {}

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def system_one(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices={
                        "local_status": SimpleNamespace(
                            choice="clear",
                            confidence=1.0,
                            probabilities={
                                "clear": 1.0,
                                "review": 0.0,
                                "rework": 0.0,
                                "unknown": 0.0,
                            },
                        )
                    },
                    nouls={
                        "concrete_issue": SimpleNamespace(noul=0.0),
                        "spec_mismatch": SimpleNamespace(noul=0.0),
                        "regression_risk": SimpleNamespace(noul=0.0),
                    },
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                    model="jev-1.13.0",
                )

        with patch.object(jev_gateway, "_sdk", return_value=(None, None, FakeClient)), patch.object(
            jev_gateway, "_build_questions", return_value={}
        ), patch.dict("os.environ", {}, clear=True):
            jev_gateway.audit_with_jev({}, object())

        self.assertEqual(captured["model"], "jev-1.13.0")

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
        for key in ("concrete_issue", "spec_mismatch", "regression_risk"):
            self.assertIn("監査対象データ", questions[key].instructions)

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

    def test_semantically_incomplete_status_probabilities_are_rejected(self):
        response = SimpleNamespace(
            choices={
                "local_status": SimpleNamespace(
                    choice="clear", confidence=1.0, probabilities={"clear": 1.0}
                )
            },
            nouls={
                "concrete_issue": SimpleNamespace(noul=0.0),
                "spec_mismatch": SimpleNamespace(noul=0.0),
                "regression_risk": SimpleNamespace(noul=0.0),
            },
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            model="jev-test",
        )
        with self.assertRaisesRegex(RuntimeError, "probabilities"):
            jev_gateway._serialize_response(response, 1.0)

    def test_invalid_choice_and_probability_range_are_rejected(self):
        response = SimpleNamespace(
            choices={
                "local_status": SimpleNamespace(
                    choice="maybe",
                    confidence=1.0,
                    probabilities={
                        "clear": 0.25,
                        "review": 0.25,
                        "rework": 0.25,
                        "unknown": 0.25,
                    },
                )
            },
            nouls={
                "concrete_issue": SimpleNamespace(noul=0.0),
                "spec_mismatch": SimpleNamespace(noul=1.2),
                "regression_risk": SimpleNamespace(noul=0.0),
            },
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            model="jev-test",
        )
        with self.assertRaisesRegex(RuntimeError, "choice"):
            jev_gateway._serialize_response(response, 1.0)

    def test_non_normalized_and_non_finite_probabilities_are_rejected(self):
        for probabilities in (
            {"clear": 0.4, "review": 0.2, "rework": 0.2, "unknown": 0.1},
            {"clear": math.nan, "review": 0.0, "rework": 0.0, "unknown": 1.0},
        ):
            response = SimpleNamespace(
                choices={
                    "local_status": SimpleNamespace(
                        choice="clear", confidence=1.0, probabilities=probabilities
                    )
                },
                nouls={
                    "concrete_issue": SimpleNamespace(noul=0.0),
                    "spec_mismatch": SimpleNamespace(noul=0.0),
                    "regression_risk": SimpleNamespace(noul=0.0),
                },
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                model="jev-test",
            )
            with self.assertRaisesRegex(RuntimeError, "probabilities"):
                jev_gateway._serialize_response(response, 1.0)

    def test_noul_probability_range_is_rejected(self):
        response = SimpleNamespace(
            choices={
                "local_status": SimpleNamespace(
                    choice="clear",
                    confidence=1.0,
                    probabilities={
                        "clear": 1.0,
                        "review": 0.0,
                        "rework": 0.0,
                        "unknown": 0.0,
                    },
                )
            },
            nouls={
                "concrete_issue": SimpleNamespace(noul=0.0),
                "spec_mismatch": SimpleNamespace(noul=math.inf),
                "regression_risk": SimpleNamespace(noul=0.0),
            },
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            model="jev-test",
        )
        with self.assertRaisesRegex(RuntimeError, "noul"):
            jev_gateway._serialize_response(response, 1.0)

    def test_invalid_token_usage_is_rejected(self):
        response = SimpleNamespace(
            choices={
                "local_status": SimpleNamespace(
                    choice="clear",
                    confidence=1.0,
                    probabilities={
                        "clear": 1.0,
                        "review": 0.0,
                        "rework": 0.0,
                        "unknown": 0.0,
                    },
                )
            },
            nouls={
                "concrete_issue": SimpleNamespace(noul=0.0),
                "spec_mismatch": SimpleNamespace(noul=0.0),
                "regression_risk": SimpleNamespace(noul=0.0),
            },
            usage=SimpleNamespace(input_tokens=-1, output_tokens=1),
            model="jev-test",
        )
        with self.assertRaisesRegex(RuntimeError, "input_tokens"):
            jev_gateway._serialize_response(response, 1.0)


if __name__ == "__main__":
    unittest.main()
