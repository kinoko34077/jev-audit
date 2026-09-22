import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jev_audit import runtime_bridge


class _FakeResult:
    def __init__(self, status, data=None, error=None):
        self.status = status
        self.data = data
        self.error = error

    @classmethod
    def success(cls, data=None):
        return cls("success", data=data)


class _FakeError:
    def __init__(self, code, message, details=None):
        self.code = code
        self.message = message
        self.details = details or {}


class _FakeErrorException(Exception):
    def __init__(self, error):
        self.error = error
        super().__init__(error.message)


class _FakeRegistry:
    last = None

    def __init__(self):
        self.registered = {}
        _FakeRegistry.last = self

    def register(self, action_id, handler):
        self.registered[action_id] = handler

    def execute(self, request, context):
        try:
            return self.registered[request.action_id](request, context)
        except _FakeErrorException as exception:
            return _FakeResult("failed", error=exception.error)


def _runtime():
    return SimpleNamespace(
        ActionContext=lambda: object(),
        ActionError=_FakeError,
        ActionErrorException=_FakeErrorException,
        ActionRegistry=_FakeRegistry,
        ActionRequest=lambda action_id, input: SimpleNamespace(
            action_id=action_id, input=input
        ),
        ActionResult=_FakeResult,
    )


class RuntimeBridgeTests(unittest.TestCase):
    def test_without_runtime_it_uses_the_existing_audit_core(self):
        expected = object()
        with patch.object(runtime_bridge, "_load_runtime", return_value=None), patch.object(
            runtime_bridge, "_legacy_audit", return_value=expected
        ) as legacy:
            actual = runtime_bridge.run_audit(Path("repo"), profile="generic", workers=1)

        self.assertIs(expected, actual)
        legacy.assert_called_once_with(Path("repo"), profile="generic", workers=1)

    def test_runtime_path_executes_the_shared_repo_audit_action(self):
        expected = object()
        fake_runtime = SimpleNamespace(
            ActionContext=lambda: object(),
            ActionError=_FakeError,
            ActionErrorException=_FakeErrorException,
            ActionRegistry=_FakeRegistry,
            ActionRequest=lambda action_id, input: SimpleNamespace(
                action_id=action_id, input=input
            ),
            ActionResult=_FakeResult,
        )
        with patch.object(runtime_bridge, "_load_runtime", return_value=fake_runtime), patch.object(
            runtime_bridge, "_legacy_audit", return_value=expected
        ) as legacy:
            actual = runtime_bridge.run_audit(Path("repo"), profile="generic", workers=1)

        self.assertIs(expected, actual)
        self.assertIn("repo.audit", _FakeRegistry.last.registered)
        legacy.assert_called_once_with(Path("repo"), profile="generic", workers=1)

    def test_runtime_preserves_expected_input_error_codes(self):
        fake_runtime = SimpleNamespace(
            ActionContext=lambda: object(),
            ActionError=_FakeError,
            ActionErrorException=_FakeErrorException,
            ActionRegistry=_FakeRegistry,
            ActionRequest=lambda action_id, input: SimpleNamespace(
                action_id=action_id, input=input
            ),
            ActionResult=_FakeResult,
        )
        with patch.object(runtime_bridge, "_load_runtime", return_value=fake_runtime), patch.object(
            runtime_bridge,
            "_legacy_audit",
            side_effect=FileNotFoundError("profile not found"),
        ):
            with self.assertRaises(runtime_bridge.RuntimeAuditError) as raised:
                runtime_bridge.run_audit(Path("repo"), profile="missing")

        self.assertEqual("NOT_FOUND", raised.exception.error.code)

    def test_runtime_preserves_no_auditable_files_error(self):
        fake_runtime = _runtime()
        message = "No auditable text files found after exclusions"
        with patch.object(runtime_bridge, "_load_runtime", return_value=fake_runtime), patch.object(
            runtime_bridge, "_legacy_audit", side_effect=RuntimeError(message)
        ):
            with self.assertRaises(runtime_bridge.RuntimeAuditError) as raised:
                runtime_bridge.run_audit(Path("repo"))

        self.assertEqual("NO_AUDITABLE_FILES", raised.exception.error.code)
        self.assertEqual(message, raised.exception.error.message)
        self.assertEqual("builtins.RuntimeError", raised.exception.error.details["exception_type"])

    def test_runtime_preserves_provider_error_meaning_and_message(self):
        fake_runtime = _runtime()

        class TypeSafeRateLimitError(Exception):
            status = 429
            request_id = "req-test"

        error = TypeSafeRateLimitError("429 rate limit; retry later")
        with patch.object(runtime_bridge, "_load_runtime", return_value=fake_runtime), patch.object(
            runtime_bridge, "_legacy_audit", side_effect=error
        ):
            with self.assertRaises(runtime_bridge.RuntimeAuditError) as raised:
                runtime_bridge.run_audit(Path("repo"))

        self.assertEqual("PROVIDER_RATE_LIMIT", raised.exception.error.code)
        self.assertEqual(str(error), raised.exception.error.message)
        self.assertEqual(429, raised.exception.error.details["status"])
        self.assertEqual("req-test", raised.exception.error.details["request_id"])

    def test_runtime_preserves_generic_audit_error_message(self):
        fake_runtime = _runtime()
        error = OSError("provider connection closed")
        with patch.object(runtime_bridge, "_load_runtime", return_value=fake_runtime), patch.object(
            runtime_bridge, "_legacy_audit", side_effect=error
        ):
            with self.assertRaises(runtime_bridge.RuntimeAuditError) as raised:
                runtime_bridge.run_audit(Path("repo"))

        self.assertEqual("AUDIT_ERROR", raised.exception.error.code)
        self.assertEqual(str(error), raised.exception.error.message)

    @unittest.skipUnless(
        importlib.util.find_spec("kinotch_runtime"),
        "install the Runtime package or set PYTHONPATH for the actual Pilot check",
    )
    def test_actual_runtime_kernel_executes_the_audit_action(self):
        expected = object()
        with patch.object(runtime_bridge, "_legacy_audit", return_value=expected):
            actual = runtime_bridge.run_audit(Path("repo"), profile="generic", workers=1)

        self.assertIs(expected, actual)


if __name__ == "__main__":
    unittest.main()
