# Project-owned Editing Boundary

KiNoTch Base files remain common infrastructure and are not edited by this
project. During the legacy adoption, the paths declared by
`project/project.json` are the Project-owned exception:

- `../jev_audit/` — Audit Core, scanner, batching, gateway, reporting, CLI, and
  MCP implementation
- `../tests/` — Project regression tests
- `../docs/` — user and implementation documentation

The root `README.md`, `project/**`, and those declared legacy paths may be
changed when the task concerns jev-audit. `.kinotch/**`, `AGENTS.md`, and other
common Base files remain read-only for this repository. This boundary keeps the
Domain in place while making the ownership declared by the Project Manifest
actionable for future agents.
