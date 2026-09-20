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

    def test_unknown_probability_is_separate_from_review(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.0, unknown=0.95, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "unknown")
        item = aggregate["highest_risk_batches"][0]
        self.assertEqual(item["actionable_probability"], 0.0)
        self.assertEqual(item["unknown_probability"], 0.95)

    def test_split_review_and_rework_probability_prevents_false_green(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.20, review=0.45, unknown=0.25, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "review")
        self.assertGreaterEqual(aggregate["highest_risk_batches"][0]["actionable_probability"], 0.60)

    def test_unknown_below_threshold_does_not_force_review(self):
        batch = BatchAudit(
            index=1,
            paths=("a.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.0, review=0.0, unknown=0.79, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        self.assertEqual(aggregate["overall"]["status"], "clear")

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

    def test_risk_driver_identifies_signal_that_sets_risk(self):
        batch = BatchAudit(
            index=1,
            paths=("spec.md",),
            chars=10,
            result=result(concrete=0.57, rework=0.20, spec=0.83, regression=0.60),
        )
        aggregate = aggregate_batches((batch,))
        item = aggregate["highest_risk_batches"][0]
        self.assertEqual(item["risk"], 0.83)
        self.assertEqual(item["risk_driver"], "spec_mismatch")
        self.assertEqual(item["rework_probability"], 0.20)

    def test_status_trigger_keeps_actionable_batch_even_when_not_top_risk(self):
        batches = []
        for index in range(1, 11):
            batches.append(BatchAudit(
                index=index,
                paths=(f"risk{index}.py",),
                chars=10,
                result=result(concrete=0.54, rework=0.0, review=0.0, spec=0.1, regression=0.1),
            ))
        batches.append(BatchAudit(
            index=11,
            paths=("actionable.py",),
            chars=10,
            result=result(concrete=0.10, rework=0.10, review=0.85, spec=0.10, regression=0.10),
        ))

        aggregate = aggregate_batches(tuple(batches))
        self.assertEqual(aggregate["overall"]["status"], "review")
        trigger = aggregate["overall"]["status_trigger"]
        self.assertEqual(trigger["kind"], "actionable_probability")
        self.assertEqual(trigger["batch_index"], 11)
        self.assertAlmostEqual(trigger["value"], 0.95)
        self.assertNotIn(11, [item["index"] for item in aggregate["highest_risk_batches"]])

    def test_unknown_trigger_records_source_batch(self):
        batch = BatchAudit(
            index=7,
            paths=("unknown.py",),
            chars=10,
            result=result(concrete=0.1, rework=0.0, review=0.0, unknown=0.95, spec=0.1, regression=0.1),
        )
        aggregate = aggregate_batches((batch,))
        trigger = aggregate["overall"]["status_trigger"]
        self.assertEqual(trigger["kind"], "unknown_probability")
        self.assertEqual(trigger["batch_index"], 7)
        self.assertAlmostEqual(trigger["value"], 0.95)


if __name__ == "__main__":
    unittest.main()
