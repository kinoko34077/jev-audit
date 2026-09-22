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


class _FakeRegistry:
    last = None

    def __init__(self):
        self.registered = {}
        _FakeRegistry.last = self

    def register(self, action_id, handler):
        self.registered[action_id] = handler

    def execute(self, request, context):
        return self.registered[request.action_id](request, context)


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
