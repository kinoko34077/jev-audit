from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
import time
from typing import Any

from . import __version__
from .aggregate import aggregate_batches
from .batching import make_batches
from .jev_gateway import _resolve_model, audit_with_jev
from .models import AuditProfile, AuditReport, Batch, BatchAudit
from .profiles import load_profile
from .scanner import ScanOptions, scan_directory


DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_TOTAL_CHARS = 5_000_000
DEFAULT_MAX_BATCHES = 1_000
MAX_WORKERS = 32


def _batch_state(batch: Batch) -> dict[str, Any]:
    # 監査規定はquestions側へ持たせ、stateは監査対象そのものだけにする。
    # 各バッチでprofile名・説明・scan modeを重複送信しない。
    files: list[dict[str, Any]] = []
    for item in batch.files:
        entry = {
            "path": item.path,
            "truncated": item.truncated,
            "content": item.content,
        }
        if item.change:
            entry["change"] = item.change
        files.append(entry)
    return {
        "files": files,
    }


def _audit_one(
    batch: Batch,
    profile: AuditProfile,
    model: str | None,
) -> BatchAudit:
    result = audit_with_jev(_batch_state(batch), profile, model=model)
    return BatchAudit(
        index=batch.index,
        paths=tuple(batch.paths),
        chars=batch.chars,
        result=result,
    )


def _audit_batches(
    batches: tuple[Batch, ...],
    profile: AuditProfile,
    model: str | None,
    workers: int,
) -> tuple[BatchAudit, ...]:
    """Audit with at most ``workers`` requests in flight at any time."""
    if workers <= 1:
        return tuple(_audit_one(batch, profile, model) for batch in batches)

    executor = ThreadPoolExecutor(max_workers=workers)
    pending: dict[Any, Batch] = {}
    audits: list[BatchAudit] = []
    iterator = iter(batches)

    def submit_next() -> bool:
        try:
            batch = next(iterator)
        except StopIteration:
            return False
        pending[executor.submit(_audit_one, batch, profile, model)] = batch
        return True

    try:
        for _ in range(min(workers, len(batches))):
            submit_next()

        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            completed_count = len(done)
            first_error: BaseException | None = None
            for future in done:
                pending.pop(future)
                try:
                    audits.append(future.result())
                except BaseException as exc:
                    first_error = first_error or exc

            if first_error is not None:
                for future in pending:
                    future.cancel()
                raise first_error

            for _ in range(completed_count):
                if not submit_next():
                    break
    except BaseException:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise

    executor.shutdown(wait=True)
    audits.sort(key=lambda item: item.index)
    return tuple(audits)


def _coverage(scan: Any) -> dict[str, Any]:
    content_sent_chars = sum(item.chars for item in scan.files)
    content_original_chars = sum(item.original_chars for item in scan.files)
    change_chars = sum(len(item.change) for item in scan.files)
    sent_chars = content_sent_chars + change_chars
    original_chars = content_original_chars + change_chars
    files_skipped = sum(scan.skipped_counts.values())
    return {
        "files_scanned": len(scan.files),
        "file_entries_skipped": files_skipped,
        # Backward-compatible alias; this counts enumerated file entries only.
        "files_skipped": files_skipped,
        "files_considered": len(scan.files) + files_skipped,
        "files_truncated": sum(1 for item in scan.files if item.truncated),
        "excluded_directory_count": len(scan.excluded_directories),
        "sent_chars": sent_chars,
        "original_chars": original_chars,
        "content_sent_chars": content_sent_chars,
        "content_original_chars": content_original_chars,
        "change_chars": change_chars,
        "char_coverage": sent_chars / original_chars if original_chars else None,
    }


def _provenance(
    profile: AuditProfile,
    scan: Any,
    *,
    changed_only: bool,
    max_file_chars: int,
    max_file_bytes: int,
    batch_chars: int,
    requested_workers: int,
    effective_workers: int,
    batch_count: int,
    requested_model: str | None,
    max_files: int | None,
    max_total_chars: int | None,
    max_batches: int | None,
) -> dict[str, Any]:
    return {
        "tool_version": __version__,
        "requested_model": requested_model,
        "resolved_model": _resolve_model(requested_model),
        "profile_name": profile.name,
        "profile_source": profile.source,
        "profile_sha256": profile.source_sha256,
        "changed_only": changed_only,
        "max_file_chars": max_file_chars,
        "max_file_bytes": max_file_bytes,
        "batch_chars": batch_chars,
        # `workers` remains as a compatibility alias for its historical
        # effective concurrency meaning; new consumers should use the explicit
        # requested/effective fields.
        "workers": effective_workers,
        "requested_workers": requested_workers,
        "effective_workers": effective_workers,
        "batch_count": batch_count,
        "max_files": max_files,
        "max_total_chars": max_total_chars,
        "max_batches": max_batches,
        "git_head_sha": scan.git.get("head_sha"),
    }


def audit_directory(
    path: str | Path = ".",
    *,
    profile: str = "development",
    changed_only: bool = False,
    max_file_chars: int = 12_000,
    max_file_bytes: int = 2_000_000,
    batch_chars: int = 32_000,
    workers: int = 4,
    model: str | None = None,
    max_files: int | None = DEFAULT_MAX_FILES,
    max_total_chars: int | None = DEFAULT_MAX_TOTAL_CHARS,
    max_batches: int | None = DEFAULT_MAX_BATCHES,
) -> AuditReport:
    if max_file_chars <= 0:
        raise ValueError("max_file_chars must be > 0")
    if max_file_bytes <= 0:
        raise ValueError("max_file_bytes must be > 0")
    if batch_chars <= 0:
        raise ValueError("batch_chars must be > 0")
    for name, value in (
        ("max_files", max_files),
        ("max_total_chars", max_total_chars),
        ("max_batches", max_batches),
    ):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError(f"{name} must be > 0 or None")
    if type(workers) is not int or workers <= 0:
        raise ValueError("workers must be > 0")
    if workers > MAX_WORKERS:
        raise ValueError(f"workers must be <= {MAX_WORKERS}")
    requested_workers = workers

    started = time.perf_counter()

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
    coverage = _coverage(scan)
    truncated_paths = tuple(item.path for item in scan.files if item.truncated)

    if max_files is not None and len(scan.files) > max_files:
        raise ValueError(
            f"max_files exceeded: {len(scan.files)} auditable files > {max_files}"
        )
    sent_chars = sum(item.chars + len(item.change) for item in scan.files)
    if max_total_chars is not None and sent_chars > max_total_chars:
        raise ValueError(
            f"max_total_chars exceeded: {sent_chars} sent characters > {max_total_chars}"
        )

    if not scan.files:
        if not changed_only:
            raise RuntimeError("No auditable text files found after exclusions")
        provenance = _provenance(
            profile_obj,
            scan,
            changed_only=changed_only,
            max_file_chars=max_file_chars,
            max_file_bytes=max_file_bytes,
            batch_chars=batch_chars,
            requested_workers=requested_workers,
            effective_workers=0,
            batch_count=0,
            requested_model=model,
            max_files=max_files,
            max_total_chars=max_total_chars,
            max_batches=max_batches,
        )
        aggregate = aggregate_batches(())
        has_deleted_changes = bool(scan.git.get("deleted_paths"))
        has_skipped_changes = bool(scan.skipped_counts or scan.skipped_sensitive_paths)
        aggregate["overall"]["status"] = "unknown" if (has_deleted_changes or has_skipped_changes) else "clear"
        aggregate["wall_clock_ms"] = (time.perf_counter() - started) * 1000.0
        return AuditReport(
            root=scan.root,
            profile=profile_obj.name,
            files_scanned=0,
            batches=0,
            skipped_counts=scan.skipped_counts,
            skipped_sensitive_paths=scan.skipped_sensitive_paths,
            git=scan.git,
            batch_audits=(),
            aggregate=aggregate,
            truncated_paths=truncated_paths,
            skipped_paths_by_reason=scan.skipped_paths_by_reason,
            coverage=coverage,
            provenance=provenance,
            excluded_directories=scan.excluded_directories,
        )

    batches = make_batches(scan.files, batch_chars)
    if max_batches is not None and len(batches) > max_batches:
        raise ValueError(
            f"max_batches exceeded: {len(batches)} batches > {max_batches}"
        )
    effective_workers = min(requested_workers, len(batches))
    provenance = _provenance(
        profile_obj,
        scan,
        changed_only=changed_only,
        max_file_chars=max_file_chars,
        max_file_bytes=max_file_bytes,
        batch_chars=batch_chars,
        requested_workers=requested_workers,
        effective_workers=effective_workers,
        batch_count=len(batches),
        requested_model=model,
        max_files=max_files,
        max_total_chars=max_total_chars,
        max_batches=max_batches,
    )

    batch_audits = _audit_batches(tuple(batches), profile_obj, model, effective_workers)
    aggregate = aggregate_batches(batch_audits)
    aggregate["wall_clock_ms"] = (time.perf_counter() - started) * 1000.0

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
        truncated_paths=truncated_paths,
        skipped_paths_by_reason=scan.skipped_paths_by_reason,
        coverage=coverage,
        provenance=provenance,
        excluded_directories=scan.excluded_directories,
    )
