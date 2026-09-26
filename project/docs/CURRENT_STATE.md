# Current State

Base version: `0.3.8`
Project version: `0.2.12`

Last verified: 2026-09-25 — GitHub Actions Node 24 action migration

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
- Core/CLI/MCP total-work guardrails and changed-only diff context are enabled;
  missing provider token usage remains explicitly unreported with completeness
  and missing-batch metadata
- Total input guardrails include repeated question/profile instruction overhead;
  scanner snapshot accumulation stops early at file and content limits
- Changed-only Git scans do not walk unrelated repository trees to collect
  excluded-directory metadata
- Changed-only Git diff and diff-context commands disable both external diff
  helpers and textconv programs
- MCP custom profiles use the shared profile resolver, allowed-root boundary,
  and 256,000-byte size cap before profile contents are read
- Runtime opt-in without an installed or compatible Pilot dependency returns an
  explicit dependency error rather than silently using the direct path
- Reports distinguish requested/effective workers and record excluded ignored
  directories without enumerating their child files
- Git path enumeration uses NUL-delimited output for newline-safe filenames
- CLI clean changed-only no-op does not require an API key because no Jev request
  is issued
- Changed-only audits can compare an explicit base commit to the checked-out current HEAD via `--base-ref`; reports preserve exact `git_base_sha` and `git_head_sha`, and equal base/head remains provider-free
- GitHub Actions use the Node 24 based `actions/checkout@v7` and
  `actions/setup-python@v7` releases

## Default state

- `cli`: `OVERRIDE` — existing CLI is authoritative
- `mcp`: `OVERRIDE` — existing MCP server is authoritative
- `ci-test`: `OVERRIDE` — existing test workflow is authoritative

## Known constraints

- The Base workflow is an additional common verification gate; the existing
  matrix workflow remains Project-owned.
- Optional `kinotch-runtime` installation is not part of the default setup and
  is provided through the source-only `requirements-pilot.txt` file.
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
- `python -m unittest discover -s tests -v` (120 tests; Windows skips the two
  newline-filename cases)
