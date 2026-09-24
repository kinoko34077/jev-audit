from __future__ import annotations

import json
from pathlib import Path

from .models import AuditReport


STATUS_LABELS = {
    "clear": "GREEN / no concrete issue",
    "review": "YELLOW / review",
    "rework": "RED / rework",
    "unknown": "UNKNOWN / insufficient local context",
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
    trigger = overall.get("status_trigger")
    if isinstance(trigger, dict):
        kind = trigger.get("kind")
        batch_index = int(trigger.get("batch_index", 0))
        if kind == "concrete_and_rework":
            lines.append(
                f"reason : concrete={_pct(float(trigger.get('concrete_issue', 0.0)))} "
                f"and rework={_pct(float(trigger.get('rework_probability', 0.0)))} at batch #{batch_index}"
            )
        elif kind == "concrete_risk":
            lines.append(
                f"reason : risk={_pct(float(trigger.get('value', 0.0)))} "
                f"via={trigger.get('risk_driver', 'unknown')} at batch #{batch_index}"
            )
        elif kind == "actionable_probability":
            lines.append(
                f"reason : actionable={_pct(float(trigger.get('value', 0.0)))} at batch #{batch_index}"
            )
        elif kind == "unknown_probability":
            lines.append(
                f"reason : unknown={_pct(float(trigger.get('value', 0.0)))} at batch #{batch_index}"
            )
        paths = trigger.get("paths", ())
        if isinstance(paths, (list, tuple)) and paths:
            shown = ", ".join(str(path) for path in paths[:5])
            if len(paths) > 5:
                shown += f", ... (+{len(paths) - 5})"
            lines.append(f"trigger paths: {shown}")
    lines.append(f"risk   : {_pct(float(overall.get('risk', 0.0)))} (highest concrete-risk batch)")
    lines.append(f"root   : {report.root}")
    lines.append(f"profile: {report.profile}")
    lines.append(f"files  : {report.files_scanned}")
    lines.append(f"batches: {report.batches}")
    lines.append(f"model  : {report.model}")

    coverage = report.coverage
    if coverage:
        ratio = coverage.get("char_coverage")
        ratio_text = "-" if ratio is None else f"{float(ratio) * 100:.1f}%"
        lines.append(
            f"coverage: chars={int(coverage.get('sent_chars', 0))}/{int(coverage.get('original_chars', 0))} "
            f"({ratio_text}) truncated={int(coverage.get('files_truncated', 0))} "
            f"skipped={int(coverage.get('files_skipped', 0))}"
        )

    provenance = report.provenance
    if provenance:
        lines.append(
            f"provenance: tool={provenance.get('tool_version', 'unknown')} "
            f"model={provenance.get('resolved_model', 'unknown')} "
            f"git={provenance.get('git_head_sha') or 'unknown'}"
        )

    usage = aggregate.get("usage", {})
    lines.append(
        f"tokens : input={int(usage.get('input_tokens', 0))} "
        f"output={int(usage.get('output_tokens', 0))}"
    )
    lines.append(
        f"elapsed: {float(aggregate.get('wall_clock_ms', 0.0)):.1f} ms (wall-clock)"
    )
    lines.append(
        f"api work: {float(aggregate.get('total_batch_latency_ms', 0.0)):.1f} ms "
        "(sum of parallel batch requests)"
    )

    lines.append("")
    lines.append("[concrete risk signals]")
    for name in ("concrete_issue", "spec_mismatch", "regression_risk"):
        stats = aggregate.get("signals", {}).get(name, {})
        lines.append(
            f"  {name:24s} max={_pct(float(stats.get('max', 0.0)))} "
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
                f"via={item.get('risk_driver', 'unknown')} "
                f"concrete={_pct(float(item['concrete_issue']))} "
                f"rework={_pct(float(item['rework_probability']))} "
                f"actionable={_pct(float(item['actionable_probability']))} "
                f"unknown={_pct(float(item['unknown_probability']))} :: {shown}"
            )

    if report.skipped_counts:
        lines.append("")
        lines.append("[skipped]")
        for reason, count in sorted(report.skipped_counts.items()):
            lines.append(f"  {reason:28s} {count}")

    if report.skipped_sensitive_paths:
        lines.append("  sensitive file contents were NOT sent to Jev")
    deleted_paths = report.git.get("deleted_paths", ())
    if deleted_paths:
        lines.append("  deleted file contents were not available to audit")

    lines.append("")
    lines.append("Fast probabilistic screening only; use detailed review/tests for final verification.")
    return "\n".join(lines)


def write_json(report: AuditReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
