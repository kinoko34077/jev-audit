import unittest

from jev_audit.aggregate import aggregate_batches
from jev_audit.models import BatchAudit, JevResult


def result(*, concrete=0.1, rework=0.1, context=0.1, spec=0.1, regression=0.1, hidden=0.1):
    return JevResult(
        model="jev-test",
        elapsed_ms=10.0,
        usage={"input_tokens": 100, "output_tokens": 10},
        choices={
            "local_status": {
                "choice": "clear",
                "confidence": 0.8,
                "probabilities": {"clear": 1.0 - rework, "review": 0.0, "rework": rework, "unknown": 0.0},
            },
            "dominant_rule": {
                "choice": "none",
                "confidence": 0.8,
                "probabilities": {"none": 0.8, "unknown": 0.1, "DEV-TEST": 0.1},
            },
            "dominant_issue_area": {
                "choice": "none",
                "confidence": 0.8,
                "probabilities": {"none": 0.8, "unknown": 0.2},
            },
        },
        nouls={
            "concrete_issue": concrete,
            "spec_mismatch": spec,
            "regression_risk": regression,
            "hidden_assumption": hidden,
            "context_insufficient": context,
        },
        scores={"severity": {"score": 1.0, "confidence": 0.8, "probabilities": {}, "legend": {}}},
    )


class AggregateTests(unittest.TestCase):
    def test_context_shortage_is_not_defect_risk(self):
        batch = BatchAudit(index=1, paths=("a.py",), chars=10, result=result(context=0.98))
        aggregate = aggregate_batches((batch,))
        self.assertLess(aggregate["overall"]["risk"], 0.55)
        self.assertEqual(aggregate["overall"]["status"], "review")
        self.assertGreater(aggregate["context_insufficient"]["mean"], 0.9)

    def test_concrete_issue_and_rework_can_raise_red(self):
        batch = BatchAudit(index=1, paths=("a.py",), chars=10, result=result(concrete=0.91, rework=0.81))
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "rework")
        self.assertGreater(aggregate["overall"]["risk"], 0.8)


if __name__ == "__main__":
    unittest.main()
