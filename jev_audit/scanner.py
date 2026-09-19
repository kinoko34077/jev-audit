from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Iterable

from .models import FileSnapshot, ScanResult


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    "htmlcov",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vs",
}

KNOWN_LOCK_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "cargo.lock",
    "uv.lock",
    "poetry.lock",
    "composer.lock",
}

SENSITIVE_BASENAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}

SENSITIVE_SUFFIXES = {
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
}


@dataclass(frozen=True)
class ScanOptions:
    changed_only: bool = False
    max_file_chars: int = 12_000
    max_file_bytes: int = 2_000_000


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _is_git_root(root: Path) -> bool:
    result = _run_git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == root.resolve()
    except OSError:
        return False


def _git_candidates(root: Path, changed_only: bool) -> list[Path] | None:
    if not _is_git_root(root):
        if changed_only:
            raise ValueError("--changed-only requires the target path itself to be a Git repository root")
        return None

    if changed_only:
        changed = _run_git(root, "diff", "--name-only", "HEAD", "--")
        untracked = _run_git(root, "ls-files", "--others", "--exclude-standard")
        names = set(changed.stdout.splitlines()) | set(untracked.stdout.splitlines())
    else:
        listed = _run_git(root, "ls-files", "-co", "--exclude-standard")
        names = set(listed.stdout.splitlines())

    result: list[Path] = []
    for name in sorted(name for name in names if name.strip()):
        path = root / name
        if path.is_file() and not path.is_symlink():
            result.append(path)
    return result


def _walk_candidates(root: Path) -> Iterable[Path]:
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS]
        base = Path(current_root)
        for name in files:
            path = base / name
            if not path.is_symlink():
                yield path


def _skip_reason(path: Path, root: Path, max_file_bytes: int) -> str | None:
    rel_parts = path.relative_to(root).parts
    if any(part.lower() in IGNORED_DIRS for part in rel_parts[:-1]):
        return "ignored_directory"

    name_lower = path.name.lower()
    if name_lower in KNOWN_LOCK_FILES:
        return "lock_or_generated"
    if name_lower in SENSITIVE_BASENAMES or name_lower.startswith(".env."):
        return "sensitive"
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        return "sensitive"

    try:
        if path.stat().st_size > max_file_bytes:
            return "too_large"
    except OSError:
        return "unreadable"
    return None


def _decode_text(raw: bytes) -> str | None:
    if b"\x00" in raw[:8192]:
        return None
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    if max_chars < 200:
        return text[:max_chars], True
    head = int(max_chars * 0.72)
    tail = max_chars - head
    marker = "\n\n... [jev-audit: middle truncated] ...\n\n"
    room = max_chars - len(marker)
    head = max(1, int(room * 0.72))
    tail = max(1, room - head)
    return text[:head] + marker + text[-tail:], True


def _git_metadata(root: Path) -> dict:
    if not _is_git_root(root):
        return {"is_git_repo": False}

    status = _run_git(root, "status", "--porcelain=v1")
    diff_stat = _run_git(root, "diff", "--stat", "HEAD", "--")
    branch = _run_git(root, "branch", "--show-current")
    head = _run_git(root, "rev-parse", "HEAD")
    return {
        "is_git_repo": True,
        "branch": branch.stdout.strip() or None,
        "head": head.stdout.strip() or None,
        "status": status.stdout[:20_000],
        "diff_stat": diff_stat.stdout[:20_000],
    }


def scan_directory(root: Path, options: ScanOptions) -> ScanResult:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    git_paths = _git_candidates(root, options.changed_only)
    candidates = git_paths if git_paths is not None else sorted(_walk_candidates(root))

    skipped = Counter()
    sensitive_paths: list[str] = []
    snapshots: list[FileSnapshot] = []

    for path in candidates:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            skipped["outside_root"] += 1
            continue

        reason = _skip_reason(path, root, options.max_file_bytes)
        if reason:
            skipped[reason] += 1
            if reason == "sensitive":
                sensitive_paths.append(rel)
            continue

        try:
            raw = path.read_bytes()
        except OSError:
            skipped["unreadable"] += 1
            continue

        text = _decode_text(raw)
        if text is None:
            skipped["binary_or_unknown_encoding"] += 1
            continue

        clipped, truncated = _truncate_text(text, options.max_file_chars)
        snapshots.append(
            FileSnapshot(
                path=rel,
                content=clipped,
                chars=len(clipped),
                original_chars=len(text),
                truncated=truncated,
            )
        )

    return ScanResult(
        root=str(root),
        files=tuple(snapshots),
        skipped_counts=dict(sorted(skipped.items())),
        skipped_sensitive_paths=tuple(sorted(sensitive_paths)),
        git=_git_metadata(root),
    )
