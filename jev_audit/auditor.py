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


def _batch_state(batch: Batch, profile: AuditProfile, root: str, changed_only: bool) -> dict[str, Any]:
    # 規定全文やGit status等を毎バッチへ重複送信しない。
    # 監査規定はquestions側へ埋め込み、stateは監査対象だけに寄せる。
    return {
        "audit_profile": profile.name,
        "profile_description": profile.description,
        "root": root,
        "scan_mode": "changed_only" if changed_only else "directory",
        "files": [
            {
                "path": item.path,
                "truncated": item.truncated,
                "content": item.content,
            }
            for item in batch.files
        ],
    }


def _audit_one(
    batch: Batch,
    profile: AuditProfile,
    root: str,
    changed_only: bool,
) -> BatchAudit:
    result = audit_with_jev(_batch_state(batch, profile, root, changed_only), profile)
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
    batch_chars: int = 32_000,
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

    audits: list[BatchAudit] = []
    if workers == 1:
        audits = [
            _audit_one(batch, profile_obj, scan.root, changed_only)
            for batch in batches
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(
                    _audit_one,
                    batch,
                    profile_obj,
                    scan.root,
                    changed_only,
                ): batch.index
                for batch in batches
            }
            for future in as_completed(future_map):
                audits.append(future.result())
        audits.sort(key=lambda item: item.index)

    batch_audits = tuple(audits)
    aggregate = aggregate_batches(batch_audits)

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
    )
