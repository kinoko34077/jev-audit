# Project Specification

Status: active — first repository-local Base adoption

## Purpose

jev-audit audits repository directories using deterministic local checks and
optional TypeSafe AI enrichment, with CLI and MCP entry points.

## Acceptance

1. Existing CLI and MCP behavior remains unchanged.
2. Audit Core remains independent from KiNoTch Base and Runtime.
3. `knt doctor` validates the local Project Overlay and Base.
4. `knt verify` reaches the existing Python test suite.
5. Optional Runtime behavior remains opt-in.

## Ownership boundary

- Domain scanner, profiles, reports, CLI, MCP, and provider policy remain in
  the existing repository root.
- KiNoTch Base files and repository operations live under `.kinotch/`.
- The Project Manifest, contracts, and adoption state live under `project/`.
- No Domain file is moved merely to satisfy the Base structure.

## Commands

- Setup: `python -m pip install -e .`
- Test: `python -m unittest discover -s tests -v`
- Verify: `knt verify` (test fallback)

## Constraints

Credentials, external provider calls, deployment policy, and optional Runtime
installation remain Project-owned and are not encoded as Base Defaults.
