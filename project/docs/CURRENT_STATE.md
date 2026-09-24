# Current State

Base version: `0.3.8`

Last verified: 2026-09-24 — Project integration fixes and verification

## Implemented

- Repository-local KiNoTch Base v0.3.8 and Project Overlay
- CLI and MCP Surface declarations
- Structured setup and test commands mapped to the existing Python project
- Base setup installs the enabled MCP extra; `.kinotch/` is excluded from normal
  Project scans
- Existing jev-audit CLI, MCP, Audit Core, and optional Runtime bridge retained
- Existing Domain files remain at their original paths; no bulk move was performed
- Changed-only skip-only sets return a normal `unknown` report without a Jev call
- Profile, Git, provider-response, MCP scope, Runtime opt-in, coverage, and
  provenance boundaries are validated fail-closed
- CLI clean changed-only no-op does not require an API key because no Jev request
  is issued

## Default state

- `cli`: `OVERRIDE` — existing CLI is authoritative
- `mcp`: `OVERRIDE` — existing MCP server is authoritative
- `ci-test`: `OVERRIDE` — existing test workflow is authoritative

## Known constraints

- The Base workflow is an additional common verification gate; the existing
  matrix workflow remains Project-owned.
- Optional `kinotch-runtime` installation is not part of the default setup.
- Runtime execution also requires explicit `JEV_AUDIT_RUNTIME=1` opt-in.
- Provider credentials and external API behavior remain outside the Base layer.

## Next work

1. Keep future Default changes explicit and preserve existing Project overrides.
2. Consider a later path migration only as a separate, reviewed Project task.

## Verification

- `knt doctor`
- `knt base-check`
- `knt setup`
- `knt verify`
- `python -m unittest discover -s tests -v`
