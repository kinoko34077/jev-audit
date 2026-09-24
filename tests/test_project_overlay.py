import json
import unittest
from pathlib import Path


class ProjectOverlayTests(unittest.TestCase):
    def test_setup_installs_mcp_surface_and_domain_paths_are_declared(self):
        root = Path(__file__).parents[1]
        manifest = json.loads((root / "project" / "project.json").read_text(encoding="utf-8"))

        setup = manifest["commands"]["setup"]
        self.assertEqual(setup["args"][-1], ".[mcp]")
        self.assertTrue(manifest["surfaces"]["mcp"])
        self.assertEqual(manifest["paths"]["source"], "../jev_audit/")
        self.assertEqual(manifest["paths"]["tests"], "../tests/")
        self.assertEqual(manifest["paths"]["docs"], "../docs/")

    def test_pilot_git_dependency_is_source_requirements_only(self):
        root = Path(__file__).parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        pilot_requirements = root / "requirements-pilot.txt"
        self.assertNotIn("kinotch-runtime @ git+", pyproject)
        self.assertIn("kinotch-runtime @ git+", pilot_requirements.read_text(encoding="utf-8"))

    def test_windows_launcher_uses_unicode_safe_writer(self):
        root = Path(__file__).parents[1]
        launcher = (root / "install-command.ps1").read_text(encoding="utf-8")
        self.assertIn("WriteAllText", launcher)
        self.assertIn("jev-audit.ps1", launcher)
        self.assertIn("UTF8Encoding", launcher)
        self.assertIn("%*", launcher)
        self.assertIn("LASTEXITCODE", launcher)
        self.assertIn("ASCIIEncoding", launcher)
        self.assertNotIn("Set-Content -Encoding ASCII", launcher)

    def test_project_version_sources_are_synchronized(self):
        root = Path(__file__).parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        package = (root / "jev_audit" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('version = "0.2.11"', pyproject)
        self.assertIn('__version__ = "0.2.11"', package)

    def test_runtime_docs_require_installation_and_explicit_opt_in(self):
        root = Path(__file__).parents[1]
        for relative in ("README.md", "docs/RUNTIME_PILOT.md", "project/docs/CURRENT_STATE.md"):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertIn("JEV_AUDIT_RUNTIME=1", text, relative)
            self.assertIn("requirements-pilot.txt", text, relative)


if __name__ == "__main__":
    unittest.main()
