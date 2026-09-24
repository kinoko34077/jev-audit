# Project Specification

Status: active — first repository-local Base adoption

## Purpose

jev-audit audits repository directories using deterministic local checks and
batching, required TypeSafe AI judgments for auditable batches, and
deterministic aggregation, with CLI and MCP entry points. The Runtime bridge is
optional, but it wraps the same required Jev-backed Audit Core when enabled.

## Acceptance

1. Existing CLI behavior and in-root MCP behavior remain unchanged; MCP rejects
   paths outside its configured allowed root by default.
2. Audit Core remains independent from KiNoTch Base and Runtime.
3. `knt doctor` validates the local Project Overlay and Base.
4. `knt verify` reaches the existing Python test suite.
5. Runtime behavior requires explicit opt-in while non-empty audits still use
   the same Jev gateway and deterministic aggregation.
6. Bundled profiles, Git metadata, changed non-file entries, provider response
   semantics, MCP path scope, report provenance, and total-work guardrails fail
   closed at their respective boundaries.
7. changed-only regular files include bounded Git diff context when available;
   untracked and non-Git focused scans remain content-only.
8. Reports distinguish file-entry skips from excluded directories, preserve
   requested/effective worker provenance, and expose incomplete provider token
   usage without treating it as zero.

## Ownership boundary

- Domain scanner, profiles, reports, CLI, MCP, and provider policy remain in
  the existing repository root.
- The root paths declared by `project/project.json` (`jev_audit/`, `tests/`, and
  `docs/`) are Project-owned legacy paths and remain editable during this
  adoption.
- KiNoTch Base files and repository operations live under `.kinotch/`.
- The Project Manifest, contracts, and adoption state live under `project/`.
- No Domain file is moved merely to satisfy the Base structure.

## Commands

- Setup: `python -m pip install -e ".[mcp]"`
- Test: `python -m unittest discover -s tests -v`
- Verify: `knt verify` (test fallback)

## Constraints

Credentials, external provider calls, deployment policy, and optional Runtime
installation remain Project-owned and are not encoded as Base Defaults.
