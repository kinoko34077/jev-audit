from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AuditReport


STATUS_LABELS = {
    "clear": "GREEN / clear",
    "review": "YELLOW / review",
    "rework": "RED / rework",
    "insufficient_evidence": "YELLOW / insufficient evidence",
}


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:5.1f}%"


def format_report(report: AuditReport) -> str:
    lines: list[str] = []
    lines.append("=== Jev Audit ===")
    lines.append(f"status : {STATUS_LABELS.get(report.status, report.status)}")
    lines.append(f"root   : {report.root}")
    lines.append(f"profile: {report.profile}")
    lines.append(f"files  : {report.files_scanned}")
    lines.append(f"batches: {report.batches}")
    lines.append(f"model  : {report.final.model}")

    usage = report.aggregate.get("usage", {})
    final_in = report.final.usage.get("input_tokens") or 0
    final_out = report.final.usage.get("output_tokens") or 0
    total_in = int(usage.get("input_tokens", 0)) + int(final_in)
    total_out = int(usage.get("output_tokens", 0)) + int(final_out)
    total_latency = float(report.aggregate.get("total_batch_latency_ms", 0.0)) + report.final.elapsed_ms
    lines.append(f"tokens : input={total_in} output={total_out}")
    lines.append(f"api ms : {total_latency:.1f} (sum of requests, parallel batches included)")

    lines.append("")
    lines.append("[overall status probabilities]")
    status = report.final.choices.get("overall_status", {})
    for label, probability in sorted(
        status.get("probabilities", {}).items(), key=lambda x: x[1], reverse=True
    ):
        lines.append(f"  {label:24s} {_pct(float(probability))}")

    dominant = report.final.choices.get("dominant_issue_area", {})
    if dominant:
        lines.append("")
        lines.append(
            f"dominant issue area: {dominant.get('choice')} "
            f"(confidence={_pct(float(dominant.get('confidence', 0.0)))})"
        )

    lines.append("")
    lines.append("[risk / incompleteness]")
    fixed = [
        "needs_rework",
        "needs_more_validation",
        "evidence_insufficient",
        "regression_risk",
        "spec_mismatch",
        "hidden_assumption",
    ]
    for name in fixed:
        lines.append(f"  {name:26s} {_pct(report.final.nouls.get(name))}")

    severity = report.final.scores.get("severity", {})
    if severity:
        lines.append(
            f"  {'severity':26s} {float(severity.get('score', 0.0)):.2f}/4 "
            f"(confidence={_pct(float(severity.get('confidence', 0.0)))})"
        )

    rules = [
        (name.removeprefix("rule_violation__"), value)
        for name, value in report.final.nouls.items()
        if name.startswith("rule_violation__")
    ]
    rules.sort(key=lambda x: x[1], reverse=True)
    if rules:
        lines.append("")
        lines.append("[rule violation probabilities]")
        for rule_id, probability in rules:
            lines.append(f"  {rule_id:28s} {_pct(probability)}")

    high = report.aggregate.get("highest_risk_batches", [])[:5]
    if high:
        lines.append("")
        lines.append("[highest-risk batches]")
        for item in high:
            shown = ", ".join(item["paths"][:5])
            if len(item["paths"]) > 5:
                shown += f", ... (+{len(item['paths']) - 5})"
            lines.append(
                f"  #{item['index']} risk={_pct(float(item['max_risk']))} "
                f"status={item['status']} :: {shown}"
            )

    if report.skipped_counts:
        lines.append("")
        lines.append("[skipped]")
        for reason, count in sorted(report.skipped_counts.items()):
            lines.append(f"  {reason:28s} {count}")

    if report.skipped_sensitive_paths:
        lines.append("  sensitive file contents were NOT sent to Jev")

    lines.append("")
    lines.append("This is a fast probabilistic audit, not proof of correctness.")
    return "\n".join(lines)


def write_json(report: AuditReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
