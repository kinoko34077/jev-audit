from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
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
    ".audit",
    ".kinotch",
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
    ".envrc",
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
    ".pem",
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


def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _is_git_root(root: Path) -> bool:
    if not _git_available():
        return False
    result = _run_git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == root.resolve()
    except OSError:
        return False


def _git_metadata_present(root: Path) -> bool:
    """Return true for both normal .git directories and worktree .git files."""
    try:
        return os.path.lexists(str(root / ".git"))
    except OSError:
        # An inaccessible metadata path is itself evidence that we must not
        # silently widen the scan to an unrestricted directory walk.
        return True


def _git_failure(operation: str, result: subprocess.CompletedProcess[str]) -> RuntimeError:
    detail = (result.stderr or result.stdout or "unknown Git error").strip()
    return RuntimeError(f"{operation} failed: {detail}")


def _git_head_exists(root: Path) -> bool:
    """Detect an unborn branch from ref state rather than localized stderr."""
    symbolic = _run_git(root, "symbolic-ref", "--quiet", "HEAD")
    if symbolic.returncode == 0:
        ref = symbolic.stdout.strip()
        if not ref:
            raise _git_failure("git symbolic-ref HEAD", symbolic)
        ref_check = _run_git(root, "show-ref", "--verify", "--quiet", ref)
        if ref_check.returncode == 0:
            return True
        if ref_check.returncode == 1:
            return False
        raise _git_failure("git show-ref HEAD", ref_check)

    if symbolic.returncode == 1:
        # Detached HEADs have no symbolic ref; verify the commit directly.
        head = _run_git(root, "rev-parse", "--verify", "HEAD")
        if head.returncode == 0:
            return True
        raise _git_failure("git rev-parse HEAD", head)
    raise _git_failure("git symbolic-ref HEAD", symbolic)


def _git_head_sha(root: Path) -> str | None:
    result = _run_git(root, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _git_stage_modes(root: Path, names: set[str]) -> dict[str, str]:
    if not names:
        return {}
    result = _run_git(root, "ls-files", "--stage", "--", *sorted(names))
    if result.returncode != 0:
        raise _git_failure("git ls-files --stage", result)
    modes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        metadata, separator, name = line.partition("\t")
        if not separator:
            continue
        fields = metadata.split()
        if fields:
            modes[name] = fields[0]
    return modes


def _git_candidates(
    root: Path, changed_only: bool
) -> tuple[list[Path], tuple[str, ...], dict[str, tuple[str, ...]], str | None] | None:
    if not _git_available():
        if _git_metadata_present(root):
            raise RuntimeError(
                "Git metadata is present but the Git executable is unavailable; refusing unrestricted directory scan"
            )
        if changed_only:
            raise ValueError("--changed-only requires the target path itself to be a Git repository root")
        return None

    if not _is_git_root(root):
        if _git_metadata_present(root):
            raise RuntimeError(
                "Git metadata is present but the repository root could not be verified; refusing unrestricted directory scan"
            )
        if changed_only:
            raise ValueError("--changed-only requires the target path itself to be a Git repository root")
        return None

    deleted_names: set[str] = set()
    head_exists: bool | None = None
    if changed_only:
        head_exists = _git_head_exists(root)
        if not head_exists:
            # HEADがまだ無い新規repoでは、stagedファイルも含めて現在存在する管理対象候補を拾う。
            listed = _run_git(root, "ls-files", "-co", "--exclude-standard")
            if listed.returncode != 0:
                raise _git_failure("git ls-files", listed)
            names = set(listed.stdout.splitlines())
        else:
            changed = _run_git(root, "diff", "--name-only", "HEAD", "--")
            if changed.returncode != 0:
                raise _git_failure("git diff HEAD", changed)
            untracked = _run_git(root, "ls-files", "--others", "--exclude-standard")
            if untracked.returncode != 0:
                raise _git_failure("git ls-files", untracked)
            changed_names = set(changed.stdout.splitlines())
            names = changed_names | set(untracked.stdout.splitlines())
            deleted_names = {
                name for name in changed_names
                if name.strip() and not os.path.lexists(str(root / name))
            }
    else:
        listed = _run_git(root, "ls-files", "-co", "--exclude-standard")
        if listed.returncode != 0:
            raise _git_failure("git ls-files", listed)
        names = set(listed.stdout.splitlines())

    result: list[Path] = []
    non_regular_names: set[str] = set()
    skipped_paths: dict[str, list[str]] = defaultdict(list)
    for name in sorted(name for name in names if name.strip()):
        path = root / name
        if path.is_symlink():
            skipped_paths["symlink_change"].append(name)
        elif path.is_file():
            result.append(path)
        elif name not in deleted_names:
            non_regular_names.add(name)

    stage_modes = _git_stage_modes(root, non_regular_names)
    for name in sorted(non_regular_names):
        reason = "gitlink_change" if stage_modes.get(name) == "160000" else "non_file_change"
        skipped_paths[reason].append(name)

    head_sha = None if head_exists is False else _git_head_sha(root)
    return (
        result,
        tuple(sorted(deleted_names)),
        {reason: tuple(sorted(paths)) for reason, paths in skipped_paths.items()},
        head_sha,
    )


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


def scan_directory(root: Path, options: ScanOptions) -> ScanResult:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    git_result = _git_candidates(root, options.changed_only)
    is_git_repo = git_result is not None
    if git_result is None:
        candidates = sorted(_walk_candidates(root))
        deleted_paths: tuple[str, ...] = ()
        pre_skipped_paths: dict[str, tuple[str, ...]] = {}
        head_sha = None
    else:
        candidates, deleted_paths, pre_skipped_paths, head_sha = git_result

    skipped = Counter()
    skipped_paths: dict[str, list[str]] = defaultdict(list)
    if deleted_paths:
        skipped["deleted_change_without_content"] += len(deleted_paths)
        skipped_paths["deleted_change_without_content"].extend(deleted_paths)
    for reason, paths in pre_skipped_paths.items():
        skipped[reason] += len(paths)
        skipped_paths[reason].extend(paths)
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
            if reason != "ignored_directory":
                skipped_paths[reason].append(rel)
            if reason == "sensitive":
                sensitive_paths.append(rel)
            continue

        try:
            raw = path.read_bytes()
        except OSError:
            skipped["unreadable"] += 1
            skipped_paths["unreadable"].append(rel)
            continue

        text = _decode_text(raw)
        if text is None:
            skipped["binary_or_unknown_encoding"] += 1
            skipped_paths["binary_or_unknown_encoding"].append(rel)
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
        git={"is_git_repo": is_git_repo, "deleted_paths": deleted_paths, "head_sha": head_sha},
        skipped_paths_by_reason={
            reason: tuple(sorted(paths)) for reason, paths in skipped_paths.items()
        },
    )
