# Current State

Last verified: 2026-09-23 — KiNoTch Base v0.3.1 Canary adoption

## Implemented

- Repository-local KiNoTch Base v0.3.1 and Project Overlay
- CLI and MCP Surface declarations
- Structured setup and test commands mapped to the existing Python project
- Existing jev-audit CLI, MCP, Audit Core, and optional Runtime bridge retained
- Existing Domain files remain at their original paths; no bulk move was performed

## Default state

- `cli`: `OVERRIDE` — existing CLI is authoritative
- `mcp`: `OVERRIDE` — existing MCP server is authoritative
- `ci-test`: `OVERRIDE` — existing test workflow is authoritative

## Known constraints

- The Base workflow is an additional common verification gate; the existing
  matrix workflow remains Project-owned.
- Optional `kinotch-runtime` installation is not part of the default setup.
- Provider credentials and external API behavior remain outside the Base layer.

## Next work

1. Confirm the repository-local Base gate on GitHub Actions.
2. Keep future Default changes explicit and preserve existing Project overrides.
3. Consider a later path migration only as a separate, reviewed Project task.

## Verification

- `knt doctor`
- `knt base-check`
- `knt setup`
- `knt verify`
- `python -m unittest discover -s tests -v`
