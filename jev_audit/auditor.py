from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .aggregate import aggregate_batches
from .batching import make_batches
from .jev_gateway import audit_with_jev
from .models import AuditProfile, AuditReport, Batch, BatchAudit
from .profiles import load_profile
from .scanner import ScanOptions, scan_directory


def _batch_state(batch: Batch, profile: AuditProfile, scan_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_profile": {
            "name": profile.name,
            "description": profile.description,
            "rules": [
                {"id": rule.id, "title": rule.title, "description": rule.description}
                for rule in profile.rules
            ],
        },
        "scope": "directory_batch",
        "scan_metadata": scan_meta,
        "files": [
            {
                "path": item.path,
                "truncated": item.truncated,
                "original_chars": item.original_chars,
                "content": item.content,
            }
            for item in batch.files
        ],
    }


def _audit_one(batch: Batch, profile: AuditProfile, scan_meta: dict[str, Any]) -> BatchAudit:
    result = audit_with_jev(_batch_state(batch, profile, scan_meta), profile, phase="batch")
    return BatchAudit(
        index=batch.index,
        paths=tuple(batch.paths),
        chars=batch.chars,
        result=result,
    )


def audit_directory(
    path: str | Path = ".",
    *,
    profile: str = "development",
    changed_only: bool = False,
    max_file_chars: int = 12_000,
    max_file_bytes: int = 2_000_000,
    batch_chars: int = 16_000,
    workers: int = 4,
) -> AuditReport:
    target = Path(path).resolve()
    profile_obj = load_profile(profile)
    scan = scan_directory(
        target,
        ScanOptions(
            changed_only=changed_only,
            max_file_chars=max_file_chars,
            max_file_bytes=max_file_bytes,
        ),
    )

    if not scan.files:
        raise RuntimeError("No auditable text files found after exclusions")

    batches = make_batches(scan.files, batch_chars)
    workers = max(1, min(workers, max(1, len(batches))))

    scan_meta = {
        "root": scan.root,
        "files_total": len(scan.files),
        "skipped_counts": scan.skipped_counts,
        "sensitive_paths_redacted": list(scan.skipped_sensitive_paths),
        "git": scan.git,
    }

    audits: list[BatchAudit] = []
    if workers == 1:
        audits = [_audit_one(batch, profile_obj, scan_meta) for batch in batches]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(_audit_one, batch, profile_obj, scan_meta): batch.index
                for batch in batches
            }
            for future in as_completed(future_map):
                audits.append(future.result())
        audits.sort(key=lambda item: item.index)

    batch_audits = tuple(audits)
    aggregate = aggregate_batches(batch_audits)

    final_state = {
        "audit_profile": {
            "name": profile_obj.name,
            "description": profile_obj.description,
            "rules": [
                {"id": rule.id, "title": rule.title, "description": rule.description}
                for rule in profile_obj.rules
            ],
        },
        "scope": "directory_final_aggregation",
        "scan_metadata": scan_meta,
        "aggregate_batch_evidence": aggregate,
        "instruction": (
            "個別バッチの確率結果を、プロジェクト全体の高速簡易監査として集約してください。"
            "確率が高い問題を無視せず、証拠不足と違反を混同しないでください。"
        ),
    }
    final = audit_with_jev(final_state, profile_obj, phase="final")

    return AuditReport(
        root=scan.root,
        profile=profile_obj.name,
        files_scanned=len(scan.files),
        batches=len(batch_audits),
        skipped_counts=scan.skipped_counts,
        skipped_sensitive_paths=scan.skipped_sensitive_paths,
        git=scan.git,
        batch_audits=batch_audits,
        aggregate=aggregate,
        final=final,
    )
