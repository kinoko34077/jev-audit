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


def _risk_details(batch: BatchAudit) -> tuple[float, str]:
    values = {
        name: float(batch.result.nouls.get(name, 0.0))
        for name in RISK_SIGNALS
    }
    if not values:
        return 0.0, "none"
    driver = max(values, key=values.get)
    return values[driver], driver


def _overall_status(ranked: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    if not ranked:
        return "unknown", None

    # REDは具体的問題とJevのrework判断が一致した場合だけ。
    red_candidates = [
        item
        for item in ranked
        if float(item.get("concrete_issue", 0.0)) >= 0.80
        and float(item.get("rework_probability", 0.0)) >= 0.60
    ]
    if red_candidates:
        trigger = max(
            red_candidates,
            key=lambda item: (
                float(item.get("concrete_issue", 0.0)),
                float(item.get("rework_probability", 0.0)),
            ),
        )
        return "rework", {
            "kind": "concrete_and_rework",
            "batch_index": int(trigger["index"]),
            "concrete_issue": float(trigger["concrete_issue"]),
            "rework_probability": float(trigger["rework_probability"]),
        }

    highest_risk = ranked[0]
    if float(highest_risk.get("risk", 0.0)) >= 0.55:
        return "review", {
            "kind": "concrete_risk",
            "batch_index": int(highest_risk["index"]),
            "value": float(highest_risk["risk"]),
            "risk_driver": str(highest_risk.get("risk_driver", "unknown")),
        }

    # review/reworkは行動対象。unknownは情報不足として別扱いにする。
    actionable = max(
        ranked,
        key=lambda item: float(item.get("actionable_probability", 0.0)),
    )
    if float(actionable.get("actionable_probability", 0.0)) >= 0.60:
        return "review", {
            "kind": "actionable_probability",
            "batch_index": int(actionable["index"]),
            "value": float(actionable["actionable_probability"]),
        }

    unknown = max(
        ranked,
        key=lambda item: float(item.get("unknown_probability", 0.0)),
    )
    if float(unknown.get("unknown_probability", 0.0)) >= 0.80:
        return "unknown", {
            "kind": "unknown_probability",
            "batch_index": int(unknown["index"]),
            "value": float(unknown["unknown_probability"]),
        }

    return "clear", None


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

        risk, risk_driver = _risk_details(batch)
        local_status_probs = result.choices.get("local_status", {}).get("probabilities", {})
        review_probability = float(local_status_probs.get("review", 0.0))
        rework_probability = float(local_status_probs.get("rework", 0.0))
        unknown_probability = float(local_status_probs.get("unknown", 0.0))
        actionable_probability = max(
            0.0,
            min(1.0, review_probability + rework_probability),
        )

        ranked_batches.append(
            {
                "index": batch.index,
                "risk": risk,
                "risk_driver": risk_driver,
                "concrete_issue": float(result.nouls.get("concrete_issue", 0.0)),
                "review_probability": review_probability,
                "rework_probability": rework_probability,
                "actionable_probability": actionable_probability,
                "unknown_probability": unknown_probability,
                "paths": list(batch.paths),
            }
        )

    ranked_batches.sort(key=lambda item: float(item["risk"]), reverse=True)
    status, status_trigger = _overall_status(ranked_batches)
    overall_risk = float(ranked_batches[0]["risk"]) if ranked_batches else 0.0

    return {
        "batch_count": len(batch_audits),
        "overall": {
            "status": status,
            "risk": overall_risk,
            "status_trigger": status_trigger,
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
