from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .models import BatchAudit


RISK_SIGNALS = (
    "concrete_issue",
    "spec_mismatch",
    "regression_risk",
    "hidden_assumption",
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
    rework_probability = float(
        batch.result.choices.get("local_status", {})
        .get("probabilities", {})
        .get("rework", 0.0)
    )
    values.append(rework_probability)
    return max(values, default=0.0)


def _overall_status(ranked: list[dict[str, Any]], context_mean: float) -> str:
    if not ranked:
        return "unknown"

    top = ranked[0]
    concrete = float(top.get("concrete_issue", 0.0))
    rework_probability = float(top.get("rework_probability", 0.0))
    risk = float(top.get("risk", 0.0))

    # REDは単発の曖昧な高確率だけでは出さず、具体的問題とrework判断の一致を要求する。
    if (concrete >= 0.80 and rework_probability >= 0.60) or rework_probability >= 0.90:
        return "rework"

    if risk >= 0.55:
        return "review"

    # 情報不足はriskとは分離するが、ほぼ全体が判断不能ならGREENとはしない。
    if context_mean >= 0.80:
        return "review"

    return "clear"


def aggregate_batches(batch_audits: tuple[BatchAudit, ...]) -> dict[str, Any]:
    signal_values: dict[str, list[float]] = defaultdict(list)
    context_values: list[float] = []
    severity_scores: list[float] = []
    rule_values: dict[str, list[float]] = defaultdict(list)
    issue_values: dict[str, list[float]] = defaultdict(list)
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

        context_values.append(float(result.nouls.get("context_insufficient", 0.0)))

        severity = result.scores.get("severity", {}).get("score")
        if isinstance(severity, (int, float)):
            severity_scores.append(float(severity))

        rule_probs = result.choices.get("dominant_rule", {}).get("probabilities", {})
        for label, probability in rule_probs.items():
            if label not in {"none", "unknown"}:
                rule_values[str(label)].append(float(probability))

        issue_probs = result.choices.get("dominant_issue_area", {}).get("probabilities", {})
        for label, probability in issue_probs.items():
            if label not in {"none", "unknown"}:
                issue_values[str(label)].append(float(probability))

        risk = _batch_risk(batch)
        rework_probability = float(
            result.choices.get("local_status", {})
            .get("probabilities", {})
            .get("rework", 0.0)
        )
        ranked_batches.append(
            {
                "index": batch.index,
                "risk": risk,
                "concrete_issue": float(result.nouls.get("concrete_issue", 0.0)),
                "rework_probability": rework_probability,
                "context_insufficient": float(result.nouls.get("context_insufficient", 0.0)),
                "paths": list(batch.paths),
                "local_status": result.choices.get("local_status", {}).get("choice"),
            }
        )

    ranked_batches.sort(key=lambda item: float(item["risk"]), reverse=True)
    context_stats = _stats(context_values)
    status = _overall_status(ranked_batches, context_stats["mean"])

    top_risks = [float(item["risk"]) for item in ranked_batches[:3]]
    overall_risk = _mean(top_risks)

    return {
        "batch_count": len(batch_audits),
        "overall": {
            "status": status,
            "risk": overall_risk,
            "peak_risk": float(ranked_batches[0]["risk"]) if ranked_batches else 0.0,
        },
        "signals": {
            name: _stats(values)
            for name, values in sorted(signal_values.items())
        },
        "context_insufficient": context_stats,
        "severity": _stats(severity_scores),
        "rule_signals": {
            name: _stats(values)
            for name, values in sorted(rule_values.items())
        },
        "issue_area_signals": {
            name: _stats(values)
            for name, values in sorted(issue_values.items())
        },
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
        },
        "total_batch_latency_ms": total_latency,
        "highest_risk_batches": ranked_batches[:10],
    }
