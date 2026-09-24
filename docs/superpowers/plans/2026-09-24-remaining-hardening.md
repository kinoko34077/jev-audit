# Remaining Audit Hardening Plan

**Goal:** Close the remaining actionable findings from the audit review without
changing the existing Audit Core status thresholds.

## Scope

- Add total file, character, batch, and worker guardrails to the Core, CLI, and
  MCP boundaries.
- Apply the MCP allowed-root policy to custom profile files as well as audit
  target directories.
- Preserve missing provider token usage as `null` instead of silently reporting
  zero.
- Generate Windows `.cmd` launchers with Unicode-safe UTF-8 encoding.
- Keep the Git-based Runtime Pilot dependency out of Python distribution
  metadata so a future PyPI upload remains valid; retain a source-install
  requirements file for the Pilot workflow.
- Include bounded changed-only diff hunks in each file state so
  `regression_risk` has before/after evidence without changing the existing
  threshold policy.

## Verification

- [x] Add focused regression tests before implementation.
- [x] Run the focused and full unittest suites.
- [x] Run compile/import checks, PowerShell parse, wheel metadata build, and
  Base setup/verification.
- [x] Commit, push, and confirm GitHub Actions for the new commit.
