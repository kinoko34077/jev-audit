import unittest

from jev_audit.aggregate import aggregate_batches
from jev_audit.models import BatchAudit, JevResult


def result(
    *,
    concrete=0.1,
    rework=0.1,
    review=0.0,
    unknown=0.0,
    spec=0.1,
    regression=0.1,
):
    clear = max(0.0, 1.0 - rework - review - unknown)
    return JevResult(
        model="jev-test",
        elapsed_ms=10.0,
        usage={"input_tokens": 100, "output_tokens": 10},
        choices={
            "local_status": {
                "choice": "clear",
                "confidence": 0.8,
                "probabilities": {
                    "clear": clear,
                    "review": review,
                    "rework": rework,
                    "unknown": unknown,
                },
            },
        },
        nouls={
            "concrete_issue": concrete,
            "spec_mismatch": spec,
            "regression_risk": regression,
        },
    )


class AggregateTests(unittest.TestCase):
    def test_concrete_issue_and_rework_can_raise_red(self):
        batch = BatchAudit(index=1, paths=("a.py",), chars=10, result=result(concrete=0.91, rework=0.81))
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "rework")
        self.assertGreater(aggregate["overall"]["risk"], 0.8)

    def test_red_batch_is_not_hidden_by_higher_non_red_risk(self):
        higher_non_red = BatchAudit(
            index=1,
            paths=("spec.md",),
            chars=10,
            result=result(concrete=0.20, rework=0.20, spec=0.95),
        )
        lower_red = BatchAudit(
            index=2,
            paths=("bug.py",),
            chars=10,
            result=result(concrete=0.90, rework=0.70, regression=0.10),
        )
        aggregate = aggregate_batches((higher_non_red, lower_red))
        self.assertEqual(aggregate["overall"]["status"], "rework")

    def test_rework_probability_alone_is_review_not_red(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.0, rework=0.91, spec=0.0, regression=0.0),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "review")
        self.assertEqual(aggregate["overall"]["risk"], 0.0)

    def test_review_probability_prevents_false_green(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.0, review=0.95, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "review")

    def test_unknown_probability_prevents_false_green(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.0, unknown=0.95, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "review")

    def test_split_non_clear_probability_prevents_false_green(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.10, review=0.45, unknown=0.35, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "review")
        self.assertGreaterEqual(aggregate["highest_risk_batches"][0]["non_clear_probability"], 0.60)

    def test_overall_risk_uses_highest_concrete_batch(self):
        severe = BatchAudit(
            index=1, paths=("bad.py",), chars=10,
            result=result(concrete=0.90, rework=0.20, spec=0.10, regression=0.10),
        )
        clean1 = BatchAudit(
            index=2, paths=("ok1.py",), chars=10,
            result=result(concrete=0.0, rework=0.0, spec=0.0, regression=0.0),
        )
        clean2 = BatchAudit(
            index=3, paths=("ok2.py",), chars=10,
            result=result(concrete=0.0, rework=0.0, spec=0.0, regression=0.0),
        )
        aggregate = aggregate_batches((severe, clean1, clean2))
        self.assertEqual(aggregate["overall"]["risk"], 0.90)


if __name__ == "__main__":
    unittest.main()
