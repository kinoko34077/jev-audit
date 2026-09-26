from __future__ import annotations

import unittest

from jev_audit.benchmark import FIXTURES, run_benchmark, score_fixture
from jev_audit.models import JevResult


EXPECTED_IDS = (
    "clear-code",
    "concrete-issue",
    "spec-mismatch",
    "regression-risk",
    "insufficient-context",
    "strong-rework",
    "benign-config-docs",
    "mild-review",
)


def result(choice="clear", *, concrete=0.0, mismatch=0.0, regression=0.0):
    return JevResult(
        model="jev-1.13.0",
        elapsed_ms=1.0,
        usage={"input_tokens": 1, "output_tokens": 1},
        choices={"local_status": {"choice": choice, "confidence": 0.9, "probabilities": {
            "clear": 1.0 if choice == "clear" else 0.0,
            "review": 1.0 if choice == "review" else 0.0,
            "rework": 1.0 if choice == "rework" else 0.0,
            "unknown": 1.0 if choice == "unknown" else 0.0,
        }}},
        nouls={"concrete_issue": concrete, "spec_mismatch": mismatch, "regression_risk": regression},
    )

class BenchmarkTests(unittest.TestCase):
    def test_fixture_ids_are_fixed_and_aligned(self):
        self.assertEqual(tuple(item.id for item in FIXTURES), EXPECTED_IDS)

    def test_score_predicates_return_binary_scores(self):
        cases = {
            "clear-code": result("clear"),
            "concrete-issue": result("review", concrete=0.9),
            "spec-mismatch": result("review", mismatch=0.9),
            "regression-risk": result("review", regression=0.9),
            "insufficient-context": result("unknown"),
            "strong-rework": result("rework", concrete=0.9),
            "benign-config-docs": result("clear"),
            "mild-review": result("review", concrete=0.3),
        }
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture.id):
                self.assertEqual(score_fixture(fixture, cases[fixture.id]), 100)
        self.assertEqual(score_fixture(FIXTURES[1], result("clear")), 0)

    def test_runner_uses_fixed_profile_and_real_resolved_model_once(self):
        calls = []
        def fake_audit(state, profile, *, model=None):
            calls.append((state, profile.name, model))
            return result("clear")
        observation = run_benchmark(0, "jev-1.13.0", audit_func=fake_audit)
        self.assertEqual(observation.fixture_id, "clear-code")
        self.assertEqual(observation.score, 100)
        self.assertIsNone(observation.error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "benchmark-v1")
        self.assertEqual(calls[0][2], "jev-1.13.0")

    def test_runner_maps_provider_failure_to_null_without_raw_message(self):
        def failing(*args, **kwargs):
            raise RuntimeError("Bearer secret provider body")
        observation = run_benchmark(1, "jev-1.13.0", audit_func=failing)
        self.assertEqual(observation.fixture_id, "concrete-issue")
        self.assertIsNone(observation.score)
        self.assertEqual(observation.error, "provider_error")
        self.assertNotIn("secret", repr(observation))


if __name__ == "__main__":
    unittest.main()
