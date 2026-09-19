from __future__ import annotations

import json
from pathlib import Path

from .models import AuditReport


STATUS_LABELS = {
    "clear": "GREEN / no concrete issue",
    "review": "YELLOW / review",
    "rework": "RED / rework",
    "unknown": "YELLOW / unknown",
}


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:5.1f}%"


def format_report(report: AuditReport) -> str:
    aggregate = report.aggregate
    overall = aggregate.get("overall", {})

    lines: list[str] = []
    lines.append("=== Jev Audit ===")
    lines.append(f"status : {STATUS_LABELS.get(report.status, report.status)}")
    lines.append(f"risk   : {_pct(float(overall.get('risk', 0.0)))} (top-3 concrete-risk mean)")
    lines.append(f"root   : {report.root}")
    lines.append(f"profile: {report.profile}")
    lines.append(f"files  : {report.files_scanned}")
    lines.append(f"batches: {report.batches}")
    lines.append(f"model  : {report.model}")

    usage = aggregate.get("usage", {})
    lines.append(
        f"tokens : input={int(usage.get('input_tokens', 0))} "
        f"output={int(usage.get('output_tokens', 0))}"
    )
    lines.append(
        f"api ms : {float(aggregate.get('total_batch_latency_ms', 0.0)):.1f} "
        "(sum of parallel batch requests)"
    )

    lines.append("")
    lines.append("[concrete risk signals]")
    for name in ("concrete_issue", "spec_mismatch", "regression_risk", "hidden_assumption"):
        stats = aggregate.get("signals", {}).get(name, {})
        lines.append(
            f"  {name:24s} max={_pct(float(stats.get('max', 0.0)))} "
            f"mean={_pct(float(stats.get('mean', 0.0)))}"
        )

    severity = aggregate.get("severity", {})
    lines.append(
        f"  {'severity':24s} max={float(severity.get('max', 0.0)):.2f}/4 "
        f"mean={float(severity.get('mean', 0.0)):.2f}/4"
    )

    context = aggregate.get("context_insufficient", {})
    lines.append("")
    lines.append("[context / evidence availability]")
    lines.append(
        f"  context_insufficient     max={_pct(float(context.get('max', 0.0)))} "
        f"mean={_pct(float(context.get('mean', 0.0)))}"
    )
    lines.append("  note: context insufficiency is NOT counted as defect risk")

    rule_signals = aggregate.get("rule_signals", {})
    ranked_rules = sorted(
        rule_signals.items(),
        key=lambda item: float(item[1].get("max", 0.0)),
        reverse=True,
    )[:5]
    if ranked_rules:
        lines.append("")
        lines.append("[rule suspicion signals]")
        for rule_id, stats in ranked_rules:
            lines.append(
                f"  {rule_id:24s} max={_pct(float(stats.get('max', 0.0)))} "
                f"mean={_pct(float(stats.get('mean', 0.0)))}"
            )

    high = aggregate.get("highest_risk_batches", [])[:5]
    if high:
        lines.append("")
        lines.append("[highest-risk batches]")
        for item in high:
            shown = ", ".join(item["paths"][:5])
            if len(item["paths"]) > 5:
                shown += f", ... (+{len(item['paths']) - 5})"
            lines.append(
                f"  #{item['index']} risk={_pct(float(item['risk']))} "
                f"concrete={_pct(float(item['concrete_issue']))} "
                f"context={_pct(float(item['context_insufficient']))} :: {shown}"
            )

    if report.skipped_counts:
        lines.append("")
        lines.append("[skipped]")
        for reason, count in sorted(report.skipped_counts.items()):
            lines.append(f"  {reason:28s} {count}")

    if report.skipped_sensitive_paths:
        lines.append("  sensitive file contents were NOT sent to Jev")

    lines.append("")
    lines.append("Fast probabilistic screening only; context shortage is separated from defect risk.")
    return "\n".join(lines)


def write_json(report: AuditReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
