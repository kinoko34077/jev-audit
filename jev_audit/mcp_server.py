from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .profiles import available_profiles, resolve_profile_reference
from .runtime_bridge import run_audit


MCP_MAX_FILE_CHARS = 100_000
MCP_MAX_FILE_BYTES = 10_000_000
MCP_MAX_BATCH_CHARS = 500_000
MCP_MAX_WORKERS = 16
MCP_MAX_FILES = 5_000
MCP_MAX_TOTAL_CHARS = 2_000_000
MCP_MAX_BATCHES = 500
MCP_MAX_CUSTOM_PROFILE_BYTES = 256_000


def _allow_any_path() -> bool:
    return os.environ.get("JEV_AUDIT_ALLOW_ANY_PATH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _allowed_root() -> Path:
    configured = os.environ.get("JEV_AUDIT_ALLOWED_ROOT", "").strip()
    claude_root = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    raw = configured or claude_root or str(Path.cwd())
    root = Path(raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"MCP allowed root does not exist or is not a directory: {root}")
    return root


def _resolve_audit_path(path: str | None) -> Path:
    """Resolve the directory requested by the MCP client.

    Priority:
    1. Explicit tool argument from the client (Codex/Claude/etc.)
    2. Claude Code's documented CLAUDE_PROJECT_DIR
    3. MCP server process working directory
    """
    if path and path.strip():
        candidate = Path(path).expanduser()
    else:
        claude_root = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        candidate = Path(claude_root).expanduser() if claude_root else Path.cwd()

    resolved = candidate.resolve()
    if not resolved.exists():
        raise ValueError(f"Audit path does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Audit path is not a directory: {resolved}")
    if not _allow_any_path():
        allowed_root = _allowed_root()
        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(
                f"Audit path is outside the MCP allowed root {allowed_root}: {resolved}"
            ) from exc
    return resolved


def _resolve_profile(profile: str) -> str:
    """Keep MCP custom profile reads inside the same trust boundary."""
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("MCP profile must be a bundled name or JSON path")
    reference = resolve_profile_reference(profile)
    if reference.bundled:
        return profile
    candidate = reference.path
    if not _allow_any_path():
        allowed_root = _allowed_root()
        try:
            candidate.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(
                f"Custom profile is outside the MCP allowed root {allowed_root}: {candidate}"
            ) from exc
    if candidate.exists():
        if not candidate.is_file():
            raise ValueError(f"Custom profile path must be a JSON file: {candidate}")
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise ValueError(f"Custom profile cannot be inspected: {candidate}") from exc
        if size > MCP_MAX_CUSTOM_PROFILE_BYTES:
            raise ValueError(
                f"Custom profile size {size} exceeds MCP profile size limit "
                f"{MCP_MAX_CUSTOM_PROFILE_BYTES} bytes: {candidate}"
            )
    return str(candidate)


def _validate_mcp_limits(
    max_file_chars: int,
    max_file_bytes: int,
    batch_chars: int,
    workers: int,
    max_files: int,
    max_total_chars: int,
    max_batches: int,
) -> None:
    limits = {
        "max_file_chars": (max_file_chars, 1, MCP_MAX_FILE_CHARS),
        "max_file_bytes": (max_file_bytes, 1, MCP_MAX_FILE_BYTES),
        "batch_chars": (batch_chars, 1, MCP_MAX_BATCH_CHARS),
        "workers": (workers, 1, MCP_MAX_WORKERS),
        "max_files": (max_files, 1, MCP_MAX_FILES),
        "max_total_chars": (max_total_chars, 1, MCP_MAX_TOTAL_CHARS),
        "max_batches": (max_batches, 1, MCP_MAX_BATCHES),
    }
    for name, (value, lower, upper) in limits.items():
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"MCP {name} must be between {lower} and {upper}")


def _server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MCP support is not installed. Run: python -m pip install -e '.[mcp]'"
        ) from exc

    mcp = MCPServer(
        "jev-audit",
        instructions=(
            "Fast probabilistic directory audit. For audit_directory, pass the active "
            "workspace/repository absolute path when known. Claude Code may omit path "
            "because CLAUDE_PROJECT_DIR is provided automatically; otherwise the server "
            "falls back to its process working directory. Paths must be under "
            "JEV_AUDIT_ALLOWED_ROOT (or the resolved project root) unless the explicit "
            "JEV_AUDIT_ALLOW_ANY_PATH=1 opt-out is configured; custom profile paths "
            f"follow the same boundary and are limited to {MCP_MAX_CUSTOM_PROFILE_BYTES} bytes."
        ),
    )

    @mcp.tool()
    def audit_directory(
        path: str | None = None,
        profile: str = "development",
        changed_only: bool = False,
        max_file_chars: int = 12_000,
        max_file_bytes: int = 2_000_000,
        batch_chars: int = 32_000,
        workers: int = 4,
        model: str | None = None,
        max_files: int = MCP_MAX_FILES,
        max_total_chars: int = MCP_MAX_TOTAL_CHARS,
        max_batches: int = MCP_MAX_BATCHES,
    ) -> dict[str, Any]:
        """Audit a directory with Jev.

        Pass the caller's active workspace/repository directory in ``path`` when known.
        If omitted, Claude Code's ``CLAUDE_PROJECT_DIR`` is used when available, then
        the MCP server process working directory.
        """
        target = _resolve_audit_path(path)
        profile = _resolve_profile(profile)
        _validate_mcp_limits(
            max_file_chars,
            max_file_bytes,
            batch_chars,
            workers,
            max_files,
            max_total_chars,
            max_batches,
        )
        return run_audit(
            target,
            profile=profile,
            changed_only=changed_only,
            max_file_chars=max_file_chars,
            max_file_bytes=max_file_bytes,
            batch_chars=batch_chars,
            workers=workers,
            model=model,
            max_files=max_files,
            max_total_chars=max_total_chars,
            max_batches=max_batches,
        ).to_dict()

    @mcp.tool()
    def list_profiles() -> list[str]:
        """List bundled audit profile names."""
        return available_profiles()

    return mcp


mcp = _server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
