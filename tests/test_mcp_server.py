from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class _FakeMCPServer:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.tools = {}

    def tool(self):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate

    def run(self):
        return None


def _load_module():
    fake_mcp = types.ModuleType("mcp")
    fake_server = types.ModuleType("mcp.server")
    fake_mcpserver = types.ModuleType("mcp.server.mcpserver")
    fake_mcpserver.MCPServer = _FakeMCPServer

    prior = {name: sys.modules.get(name) for name in ("mcp", "mcp.server", "mcp.server.mcpserver")}
    sys.modules["mcp"] = fake_mcp
    sys.modules["mcp.server"] = fake_server
    sys.modules["mcp.server.mcpserver"] = fake_mcpserver
    try:
        path = Path(__file__).parents[1] / "jev_audit" / "mcp_server.py"
        spec = importlib.util.spec_from_file_location("jev_audit.mcp_server_test", path)
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "jev_audit"
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in prior.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class MCPPathResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_explicit_path_has_priority(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as claude:
            explicit = Path(allowed) / "workspace"
            explicit.mkdir()
            with patch.dict(
                os.environ,
                {"JEV_AUDIT_ALLOWED_ROOT": allowed, "CLAUDE_PROJECT_DIR": claude},
                clear=False,
            ):
                self.assertEqual(self.mod._resolve_audit_path(str(explicit)), explicit.resolve())

    def test_uses_claude_project_dir_when_path_omitted(self):
        with TemporaryDirectory() as claude:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": claude}, clear=False):
                self.assertEqual(self.mod._resolve_audit_path(None), Path(claude).resolve())

    def test_falls_back_to_process_cwd(self):
        with TemporaryDirectory() as cwd:
            old = Path.cwd()
            try:
                os.chdir(cwd)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(self.mod._resolve_audit_path(None), Path(cwd).resolve())
            finally:
                os.chdir(old)

    def test_rejects_file_path(self):
        with TemporaryDirectory() as root:
            file_path = Path(root) / "x.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.mod._resolve_audit_path(str(file_path))

    def test_rejects_path_outside_allowed_root(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False):
                with self.assertRaisesRegex(ValueError, "allowed root"):
                    self.mod._resolve_audit_path(outside)

    def test_rejects_custom_profile_outside_allowed_root(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            profile = Path(outside) / "custom.json"
            profile.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False):
                with self.assertRaisesRegex(ValueError, "Custom profile"):
                    self.mod._resolve_profile(str(profile))

    def test_bundled_profile_is_not_shadowed_by_outside_cwd(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            shadow = Path(outside) / "development.json"
            shadow.write_text("not-json", encoding="utf-8")
            old = Path.cwd()
            try:
                os.chdir(outside)
                with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False):
                    self.assertEqual(self.mod._resolve_profile("development"), "development")
            finally:
                os.chdir(old)

    def test_allows_custom_profile_inside_allowed_root(self):
        with TemporaryDirectory() as allowed:
            profile = Path(allowed) / "custom.json"
            profile.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False):
                self.assertEqual(self.mod._resolve_profile(str(profile)), str(profile.resolve()))

    def test_rejects_custom_profile_before_reading_outside_root(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            profile = Path(outside) / "custom.json"
            profile.write_text("not-json", encoding="utf-8")
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False), patch.object(
                Path, "read_text", side_effect=AssertionError("profile bytes must not be read")
            ):
                with self.assertRaisesRegex(ValueError, "Custom profile"):
                    self.mod._resolve_profile(str(profile))

    def test_allows_custom_profile_outside_root_only_with_opt_out(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            profile = Path(outside) / "custom.json"
            profile.write_text("{}", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"JEV_AUDIT_ALLOWED_ROOT": allowed, "JEV_AUDIT_ALLOW_ANY_PATH": "1"},
                clear=False,
            ):
                self.assertEqual(self.mod._resolve_profile(str(profile)), str(profile.resolve()))

    def test_rejects_oversized_custom_profile(self):
        with TemporaryDirectory() as allowed:
            profile = Path(allowed) / "large.json"
            profile.write_bytes(b"x" * (self.mod.MCP_MAX_CUSTOM_PROFILE_BYTES + 1))
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": allowed}, clear=False):
                with self.assertRaisesRegex(ValueError, "profile size"):
                    self.mod._resolve_profile(str(profile))

    def test_explicit_any_path_opt_out_is_required_for_outside_root(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
            with patch.dict(
                os.environ,
                {"JEV_AUDIT_ALLOWED_ROOT": allowed, "JEV_AUDIT_ALLOW_ANY_PATH": "1"},
                clear=False,
            ):
                self.assertEqual(self.mod._resolve_audit_path(outside), Path(outside).resolve())

    def test_mcp_limits_have_hard_caps(self):
        tool = self.mod.mcp.tools["audit_directory"]
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": root}, clear=False):
                with self.assertRaisesRegex(ValueError, "max_file_chars"):
                    tool(path=root, max_file_chars=self.mod.MCP_MAX_FILE_CHARS + 1)
                with self.assertRaisesRegex(ValueError, "workers"):
                    tool(path=root, workers=self.mod.MCP_MAX_WORKERS + 1)
                with self.assertRaisesRegex(ValueError, "max_total_chars"):
                    tool(path=root, max_total_chars=self.mod.MCP_MAX_TOTAL_CHARS + 1)
                with self.assertRaisesRegex(ValueError, "max_batches"):
                    tool(path=root, max_batches=self.mod.MCP_MAX_BATCHES + 1)
                with self.assertRaisesRegex(ValueError, "max_files"):
                    tool(path=root, max_files=self.mod.MCP_MAX_FILES + 1)

    def test_server_instructions_tell_client_to_pass_workspace(self):
        instructions = self.mod.mcp.kwargs.get("instructions", "")
        self.assertIn("workspace/repository absolute path", instructions)

    def test_tool_passes_resolved_explicit_path_to_core(self):
        class _Report:
            def to_dict(self):
                return {"ok": True}

        with TemporaryDirectory() as root:
            captured = {}

            def fake_run(path, **kwargs):
                captured["path"] = path
                captured["kwargs"] = kwargs
                return _Report()

            tool = self.mod.mcp.tools["audit_directory"]
            with patch.object(self.mod, "run_audit", fake_run):
                with patch.dict(os.environ, {"JEV_AUDIT_ALLOWED_ROOT": root}, clear=False):
                    result = tool(path=root, profile="generic", changed_only=True)

            self.assertEqual(result, {"ok": True})
            self.assertEqual(captured["path"], Path(root).resolve())
            self.assertEqual(captured["kwargs"]["profile"], "generic")
            self.assertTrue(captured["kwargs"]["changed_only"])


if __name__ == "__main__":
    unittest.main()
