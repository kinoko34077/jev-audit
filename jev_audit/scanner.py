from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess

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

MAX_CHANGE_CHARS = 20_000


@dataclass(frozen=True)
class ScanOptions:
    changed_only: bool = False
    base_ref: str | None = None
    max_file_chars: int = 12_000
    max_file_bytes: int = 2_000_000
    max_files: int | None = None
    max_total_chars: int | None = None


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


def _git_resolve_commit(root: Path, ref: str) -> str:
    result = _run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if result.returncode != 0:
        raise _git_failure(f"git rev-parse {ref}", result)
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"git rev-parse {ref} returned an empty commit SHA")
    return value


def _parse_git_nul_paths(output: str) -> list[str]:
    """Parse Git's NUL-delimited path output without newline ambiguity."""
    return [part for part in output.split("\0") if part]


def _parse_git_stage_modes(output: str) -> dict[str, str]:
    """Parse ``git ls-files --stage -z`` entries into path-to-mode values."""
    modes: dict[str, str] = {}
    for entry in output.split("\0"):
        if not entry:
            continue
        metadata, separator, name = entry.partition("\t")
        if not separator:
            continue
        fields = metadata.split()
        if fields:
            modes[name] = fields[0]
    return modes


def _excluded_directory_for_name(name: str) -> str | None:
    parts = Path(name).as_posix().split("/")
    for index, part in enumerate(parts[:-1]):
        if part.lower() in IGNORED_DIRS:
            return "/".join(parts[: index + 1])
    return None


def _collect_excluded_directories(root: Path) -> tuple[str, ...]:
    """Discover ignored directories without descending into their contents."""
    excluded_directories: set[str] = set()
    for current_root, dirs, _files in os.walk(root):
        base = Path(current_root)
        kept_dirs: list[str] = []
        for directory in dirs:
            if directory.lower() in IGNORED_DIRS:
                excluded_directories.add((base / directory).relative_to(root).as_posix())
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs
    return tuple(sorted(excluded_directories))


def _git_stage_modes(root: Path, names: set[str]) -> dict[str, str]:
    if not names:
        return {}
    result = _run_git(root, "ls-files", "--stage", "-z", "--", *sorted(names))
    if result.returncode != 0:
        raise _git_failure("git ls-files --stage", result)
    return _parse_git_stage_modes(result.stdout)


def _git_change_by_path(
    root: Path, names: set[str], *, base_sha: str | None = None
) -> dict[str, str]:
    """Return bounded before/after hunks for changed regular files."""
    if not names:
        return {}
    diff_range = (base_sha, "HEAD") if base_sha is not None else ("HEAD",)
    result = _run_git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--unified=80",
        *diff_range,
        "--",
        *sorted(names),
    )
    operation = f"git diff {base_sha} HEAD" if base_sha is not None else "git diff HEAD"
    if result.returncode != 0:
        raise _git_failure(operation, result)

    changes: dict[str, str] = {}
    section: list[str] = []
    current_path: str | None = None

    def flush() -> None:
        if current_path is None or not section:
            return
        value = "".join(section)
        changes[current_path] = value[:MAX_CHANGE_CHARS]

    for line in result.stdout.splitlines(keepends=True):
        if line.startswith("diff --git "):
            flush()
            section = [line]
            current_path = None
            continue
        if not section:
            continue
        section.append(line)
        if line.startswith("+++ b/"):
            current_path = line[6:].rstrip("\r\n")
    flush()
    return changes


def _git_candidates(
    root: Path, changed_only: bool, base_ref: str | None = None
) -> tuple[
    list[Path],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
    str | None,
    str | None,
    dict[str, str],
    tuple[str, ...],
] | None:
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
    base_sha: str | None = None
    head_exists: bool | None = None
    if changed_only:
        head_exists = _git_head_exists(root)
        if base_ref is not None:
            if not head_exists:
                raise ValueError("base_ref requires an existing HEAD commit")
            base_sha = _git_resolve_commit(root, base_ref)
            changed = _run_git(
                root,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                base_sha,
                "HEAD",
                "--",
            )
            if changed.returncode != 0:
                raise _git_failure(f"git diff {base_sha} HEAD", changed)
            changed_names = set(_parse_git_nul_paths(changed.stdout))
            names = changed_names
            deleted_names = {
                name for name in changed_names
                if name.strip() and not os.path.lexists(str(root / name))
            }
        elif not head_exists:
            listed = _run_git(root, "ls-files", "-co", "--exclude-standard", "-z")
            if listed.returncode != 0:
                raise _git_failure("git ls-files", listed)
            names = set(_parse_git_nul_paths(listed.stdout))
        else:
            changed = _run_git(
                root,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                "HEAD",
                "--",
            )
            if changed.returncode != 0:
                raise _git_failure("git diff HEAD", changed)
            untracked = _run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
            if untracked.returncode != 0:
                raise _git_failure("git ls-files", untracked)
            changed_names = set(_parse_git_nul_paths(changed.stdout))
            names = changed_names | set(_parse_git_nul_paths(untracked.stdout))
            deleted_names = {
                name for name in changed_names
                if name.strip() and not os.path.lexists(str(root / name))
            }
    else:
        listed = _run_git(root, "ls-files", "-co", "--exclude-standard", "-z")
        if listed.returncode != 0:
            raise _git_failure("git ls-files", listed)
        names = set(_parse_git_nul_paths(listed.stdout))

    result: list[Path] = []
    non_regular_names: set[str] = set()
    skipped_paths: dict[str, list[str]] = defaultdict(list)
    excluded_directories: set[str] = set()
    if not changed_only:
        excluded_directories.update(_collect_excluded_directories(root))
    excluded_directories.update(
        excluded
        for name in names
        if (excluded := _excluded_directory_for_name(name)) is not None
    )
    deleted_names = {
        name for name in deleted_names if _excluded_directory_for_name(name) is None
    }
    for name in sorted(name for name in names if name.strip()):
        if _excluded_directory_for_name(name) is not None:
            continue
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

    change_by_path: dict[str, str] = {}
    if changed_only and head_exists and result:
        change_by_path = _git_change_by_path(
            root,
            {path.relative_to(root).as_posix() for path in result},
            base_sha=base_sha,
        )
    head_sha = None if head_exists is False else _git_head_sha(root)
    return (
        result,
        tuple(sorted(deleted_names)),
        {reason: tuple(sorted(paths)) for reason, paths in skipped_paths.items()},
        head_sha,
        base_sha,
        change_by_path,
        tuple(sorted(excluded_directories)),
    )


def _walk_candidates(root: Path) -> tuple[list[Path], tuple[str, ...]]:
    candidates: list[Path] = []
    excluded_directories: set[str] = set()
    for current_root, dirs, files in os.walk(root):
        base = Path(current_root)
        kept_dirs: list[str] = []
        for directory in dirs:
            if directory.lower() in IGNORED_DIRS:
                excluded_directories.add((base / directory).relative_to(root).as_posix())
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for name in files:
            path = base / name
            if not path.is_symlink():
                candidates.append(path)
    return candidates, tuple(sorted(excluded_directories))


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
    for name, value in (
        ("max_files", options.max_files),
        ("max_total_chars", options.max_total_chars),
    ):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError(f"{name} must be > 0 or None")

    if options.base_ref is not None and not options.changed_only:
        raise ValueError("base_ref requires changed_only=True")

    git_result = _git_candidates(root, options.changed_only, options.base_ref)
    is_git_repo = git_result is not None
    if git_result is None:
        candidates, excluded_directories = _walk_candidates(root)
        deleted_paths: tuple[str, ...] = ()
        pre_skipped_paths: dict[str, tuple[str, ...]] = {}
        head_sha = None
        base_sha = None
        change_by_path: dict[str, str] = {}
    else:
        (
            candidates,
            deleted_paths,
            pre_skipped_paths,
            head_sha,
            base_sha,
            change_by_path,
            excluded_directories,
        ) = git_result

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
    scanned_chars = 0

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
        change = change_by_path.get(rel, "")
        if options.max_files is not None and len(snapshots) >= options.max_files:
            raise ValueError(
                f"max_files exceeded during scan: more than {options.max_files} auditable files"
            )
        if options.max_total_chars is not None:
            next_chars = scanned_chars + len(clipped) + len(change)
            if next_chars > options.max_total_chars:
                raise ValueError(
                    "max_total_chars exceeded during scan: "
                    f"{next_chars} sent characters > {options.max_total_chars}"
                )
            scanned_chars = next_chars
        snapshots.append(
            FileSnapshot(
                path=rel,
                content=clipped,
                chars=len(clipped),
                original_chars=len(text),
                truncated=truncated,
                change=change,
            )
        )

    git_metadata = {"is_git_repo": is_git_repo, "deleted_paths": deleted_paths, "head_sha": head_sha}
    if base_sha is not None:
        git_metadata["base_sha"] = base_sha

    return ScanResult(
        root=str(root),
        files=tuple(snapshots),
        skipped_counts=dict(sorted(skipped.items())),
        skipped_sensitive_paths=tuple(sorted(sensitive_paths)),
        git=git_metadata,
        skipped_paths_by_reason={
            reason: tuple(sorted(paths)) for reason, paths in skipped_paths.items()
        },
        excluded_directories=excluded_directories,
    )
