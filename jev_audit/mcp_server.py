from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .profiles import available_profiles
from .runtime_bridge import run_audit


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
    return resolved


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
            "falls back to its process working directory."
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
    ) -> dict[str, Any]:
        """Audit a directory with Jev.

        Pass the caller's active workspace/repository directory in ``path`` when known.
        If omitted, Claude Code's ``CLAUDE_PROJECT_DIR`` is used when available, then
        the MCP server process working directory.
        """
        target = _resolve_audit_path(path)
        return run_audit(
            target,
            profile=profile,
            changed_only=changed_only,
            max_file_chars=max_file_chars,
            max_file_bytes=max_file_bytes,
            batch_chars=batch_chars,
            workers=workers,
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
