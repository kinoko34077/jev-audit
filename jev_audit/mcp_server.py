from __future__ import annotations

from typing import Any

from .auditor import audit_directory as run_audit
from .profiles import available_profiles


def _server():
    try:
        from mcp.server import MCPServer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MCP support is not installed. Run: python -m pip install -e '.[mcp]'"
        ) from exc

    mcp = MCPServer("jev-audit")

    @mcp.tool()
    def audit_directory(
        path: str = ".",
        profile: str = "development",
        changed_only: bool = False,
        max_file_chars: int = 12_000,
        max_file_bytes: int = 2_000_000,
        batch_chars: int = 32_000,
        workers: int = 4,
    ) -> dict[str, Any]:
        """Audit a local directory with Jev and return a structured probabilistic report."""
        return run_audit(
            path,
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
