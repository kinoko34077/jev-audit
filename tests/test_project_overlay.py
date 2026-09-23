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


if __name__ == "__main__":
    unittest.main()
