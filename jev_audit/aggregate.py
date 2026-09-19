from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .models import BatchAudit


RISK_SIGNALS = (
    "concrete_issue",
    "spec_mismatch",
    "regression_risk",
)


def _mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "max": max(values, default=0.0),
        "mean": _mean(values),
    }


def _batch_risk(batch: BatchAudit) -> float:
    values = [float(batch.result.nouls.get(name, 0.0)) for name in RISK_SIGNALS]
    return max(values, default=0.0)


def _overall_status(ranked: list[dict[str, Any]]) -> str:
    if not ranked:
        return "unknown"

    # REDは具体的問題とJevのrework判断が一致した場合だけ。
    if any(
        float(item.get("concrete_issue", 0.0)) >= 0.80
        and float(item.get("rework_probability", 0.0)) >= 0.60
        for item in ranked
    ):
        return "rework"

    if float(ranked[0].get("risk", 0.0)) >= 0.55:
        return "review"

    # review/unknown/reworkへ確率が分散しても、非clear全体が強ければGREENにしない。
    if any(float(item.get("non_clear_probability", 0.0)) >= 0.60 for item in ranked):
        return "review"

    return "clear"


def aggregate_batches(batch_audits: tuple[BatchAudit, ...]) -> dict[str, Any]:
    signal_values: dict[str, list[float]] = defaultdict(list)
    total_input = 0
    total_output = 0
    total_latency = 0.0
    ranked_batches: list[dict[str, Any]] = []

    for batch in batch_audits:
        result = batch.result
        total_latency += result.elapsed_ms

        input_tokens = result.usage.get("input_tokens")
        output_tokens = result.usage.get("output_tokens")
        if isinstance(input_tokens, int):
            total_input += input_tokens
        if isinstance(output_tokens, int):
            total_output += output_tokens

        for name in RISK_SIGNALS:
            signal_values[name].append(float(result.nouls.get(name, 0.0)))

        risk = _batch_risk(batch)
        local_status_probs = result.choices.get("local_status", {}).get("probabilities", {})
        rework_probability = float(local_status_probs.get("rework", 0.0))
        clear_probability = float(local_status_probs.get("clear", 0.0))
        # Choiceの個別ラベルが将来欠けてもGREENへ誤倒ししないよう、clearの補数で扱う。
        non_clear_probability = max(0.0, min(1.0, 1.0 - clear_probability))

        ranked_batches.append(
            {
                "index": batch.index,
                "risk": risk,
                "concrete_issue": float(result.nouls.get("concrete_issue", 0.0)),
                "rework_probability": rework_probability,
                "non_clear_probability": non_clear_probability,
                "paths": list(batch.paths),
            }
        )

    ranked_batches.sort(key=lambda item: float(item["risk"]), reverse=True)
    status = _overall_status(ranked_batches)
    overall_risk = float(ranked_batches[0]["risk"]) if ranked_batches else 0.0

    return {
        "batch_count": len(batch_audits),
        "overall": {
            "status": status,
            "risk": overall_risk,
        },
        "signals": {
            name: _stats(values)
            for name, values in sorted(signal_values.items())
        },
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
        },
        "total_batch_latency_ms": total_latency,
        "highest_risk_batches": ranked_batches[:10],
    }
