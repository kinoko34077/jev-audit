from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import BatchAudit


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_batches(batch_audits: tuple[BatchAudit, ...]) -> dict[str, Any]:
    status_probabilities: dict[str, list[float]] = defaultdict(list)
    noul_values: dict[str, list[float]] = defaultdict(list)
    severity_scores: list[float] = []
    total_input = 0
    total_output = 0
    total_latency = 0.0

    for batch in batch_audits:
        result = batch.result
        total_latency += result.elapsed_ms
        input_tokens = result.usage.get("input_tokens")
        output_tokens = result.usage.get("output_tokens")
        if isinstance(input_tokens, int):
            total_input += input_tokens
        if isinstance(output_tokens, int):
            total_output += output_tokens

        status = result.choices.get("overall_status", {}).get("probabilities", {})
        for label, probability in status.items():
            status_probabilities[label].append(float(probability))

        for name, value in result.nouls.items():
            noul_values[name].append(float(value))

        severity = result.scores.get("severity", {}).get("score")
        if isinstance(severity, (int, float)):
            severity_scores.append(float(severity))

    noul_stats = {
        name: {
            "max": max(values),
            "mean": _mean(values),
        }
        for name, values in sorted(noul_values.items())
    }

    status_stats = {
        label: {
            "max": max(values),
            "mean": _mean(values),
        }
        for label, values in sorted(status_probabilities.items())
    }

    ranked_batches = []
    for batch in batch_audits:
        risks = [
            value
            for name, value in batch.result.nouls.items()
            if name.startswith("rule_violation__") or name in {
                "needs_rework",
                "needs_more_validation",
                "evidence_insufficient",
                "regression_risk",
                "spec_mismatch",
                "hidden_assumption",
            }
        ]
        max_risk = max(risks, default=0.0)
        ranked_batches.append(
            {
                "index": batch.index,
                "max_risk": max_risk,
                "paths": list(batch.paths),
                "status": batch.result.choices.get("overall_status", {}).get("choice"),
            }
        )

    ranked_batches.sort(key=lambda item: item["max_risk"], reverse=True)

    return {
        "batch_count": len(batch_audits),
        "status_probabilities": status_stats,
        "nouls": noul_stats,
        "severity": {
            "max": max(severity_scores, default=0.0),
            "mean": _mean(severity_scores),
        },
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
        },
        "total_batch_latency_ms": total_latency,
        "highest_risk_batches": ranked_batches[:20],
    }
