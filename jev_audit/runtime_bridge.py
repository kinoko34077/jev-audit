"""Optional KiNoTch Runtime boundary for the jev-audit Pilot."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .auditor import audit_directory as _legacy_audit


class RuntimeAuditError(RuntimeError):
    """A structured Runtime failure exposed at the existing audit boundary."""

    def __init__(self, error: Any) -> None:
        self.error = error
        super().__init__(f"{error.code}: {error.message}")


def _load_runtime() -> SimpleNamespace | None:
    """Load the optional Runtime package without changing the default install."""
    try:
        from kinotch_runtime import (
            ActionContext,
            ActionError,
            ActionErrorException,
            ActionRegistry,
            ActionRequest,
            ActionResult,
        )
    except ModuleNotFoundError as exc:
        if exc.name != "kinotch_runtime":
            raise
        return None

    return SimpleNamespace(
        ActionContext=ActionContext,
        ActionError=ActionError,
        ActionErrorException=ActionErrorException,
        ActionRegistry=ActionRegistry,
        ActionRequest=ActionRequest,
        ActionResult=ActionResult,
    )


def run_audit(path: str | Path = ".", **options: Any) -> Any:
    """Run the existing Audit Core, optionally through the Runtime kernel.

    The Runtime dependency is intentionally optional. A normal jev-audit
    installation follows the unchanged legacy path. The Pilot extra enables
    the shared ``repo.audit`` Action boundary used by both CLI and MCP.
    """
    runtime = _load_runtime()
    if runtime is None:
        return _legacy_audit(path, **options)

    registry = runtime.ActionRegistry()

    def audit_action(request: Any, context: Any) -> Any:
        del context
        try:
            report = _legacy_audit(request.input["path"], **request.input["options"])
        except FileNotFoundError as exc:
            raise runtime.ActionErrorException(
                runtime.ActionError(code="NOT_FOUND", message=str(exc))
            ) from exc
        except ValueError as exc:
            raise runtime.ActionErrorException(
                runtime.ActionError(code="INVALID_INPUT", message=str(exc))
            ) from exc
        return runtime.ActionResult.success(data=report)

    registry.register("repo.audit", audit_action)
    request = runtime.ActionRequest(
        action_id="repo.audit",
        input={"path": path, "options": options},
    )
    result = registry.execute(request, runtime.ActionContext())
    if result.status in {"success", "partial"}:
        return result.data
    if result.error is not None:
        raise RuntimeAuditError(result.error)
    raise RuntimeError("Runtime audit failed without a structured error")
