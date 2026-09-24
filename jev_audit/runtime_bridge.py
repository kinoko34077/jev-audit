"""Optional KiNoTch Runtime boundary for the jev-audit Pilot."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .auditor import audit_directory as _legacy_audit


class RuntimeAuditError(RuntimeError):
    """A structured Runtime failure exposed at the existing audit boundary."""

    def __init__(self, error: Any) -> None:
        self.error = error
        super().__init__(f"{error.code}: {error.message}")


_NO_AUDITABLE_FILES = "No auditable text files found after exclusions"
_PROVIDER_ERROR_CODES = {
    "TypeSafeAuthenticationError": "PROVIDER_AUTHENTICATION",
    "TypeSafePermissionDeniedError": "PROVIDER_PERMISSION_DENIED",
    "TypeSafeNotFoundError": "PROVIDER_NOT_FOUND",
    "TypeSafeBadRequestError": "PROVIDER_BAD_REQUEST",
    "TypeSafeUnprocessableEntityError": "PROVIDER_UNPROCESSABLE",
    "TypeSafeRateLimitError": "PROVIDER_RATE_LIMIT",
    "TypeSafeInternalServerError": "PROVIDER_INTERNAL",
    "TypeSafeAPIResponseValidationError": "PROVIDER_RESPONSE_INVALID",
    "TypeSafeAPIError": "PROVIDER_API",
    "TypeSafeError": "PROVIDER_CONFIG",
}


def _action_error_for_exception(runtime: SimpleNamespace, exc: Exception) -> Any:
    """Convert known audit failures before Runtime redacts unexpected exceptions."""
    exception_name = type(exc).__name__
    if isinstance(exc, FileNotFoundError):
        code = "NOT_FOUND"
    elif isinstance(exc, ValueError):
        code = "INVALID_INPUT"
    elif isinstance(exc, ModuleNotFoundError):
        code = "DEPENDENCY_ERROR"
    elif isinstance(exc, PermissionError):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, TimeoutError):
        code = "API_TIMEOUT"
    elif isinstance(exc, ConnectionError):
        code = "API_CONNECTION"
    elif isinstance(exc, RuntimeError) and str(exc) == _NO_AUDITABLE_FILES:
        code = "NO_AUDITABLE_FILES"
    else:
        code = _PROVIDER_ERROR_CODES.get(exception_name, "AUDIT_ERROR")

    details: dict[str, Any] = {
        "exception_type": f"{type(exc).__module__}.{exception_name}",
    }
    for attribute in ("status", "request_id"):
        value = getattr(exc, attribute, None)
        if isinstance(value, (str, int)) and value:
            details[attribute] = value

    message = str(exc).strip() or exception_name
    return runtime.ActionError(code=code, message=message, details=details)


def _is_known_action_error(exc: Exception) -> bool:
    """Return whether the bridge is allowed to expose this failure to Runtime."""
    if isinstance(
        exc,
        (
            FileNotFoundError,
            ValueError,
            ModuleNotFoundError,
            PermissionError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True
    if isinstance(exc, RuntimeError) and str(exc) == _NO_AUDITABLE_FILES:
        return True
    return type(exc).__name__ in _PROVIDER_ERROR_CODES


def _runtime_opted_in() -> bool:
    return os.environ.get("JEV_AUDIT_RUNTIME", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _load_runtime() -> SimpleNamespace | None:
    """Load Runtime only after explicit ``JEV_AUDIT_RUNTIME`` opt-in."""
    if not _runtime_opted_in():
        return None
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
    installation follows the unchanged legacy path. Installing the pinned Pilot
    requirements and setting the explicit opt-in enables the shared
    ``repo.audit`` Action boundary used by both CLI and MCP.
    """
    runtime = _load_runtime()
    if runtime is None:
        return _legacy_audit(path, **options)

    registry = runtime.ActionRegistry()

    def audit_action(request: Any, context: Any) -> Any:
        del context
        try:
            report = _legacy_audit(request.input["path"], **request.input["options"])
        except Exception as exc:
            if not _is_known_action_error(exc):
                raise
            raise runtime.ActionErrorException(
                _action_error_for_exception(runtime, exc)
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
