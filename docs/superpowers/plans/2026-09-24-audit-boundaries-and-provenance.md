# Audit Boundaries and Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the audit trust-boundary, fail-open, fail-fast, response-validation, MCP scope, coverage, and provenance gaps identified in the current audit review.

**Architecture:** Keep the existing Audit Core as the single orchestration path. Harden profile resolution and Git candidate enumeration at the scanner/profile boundaries, validate provider results before aggregation, bound concurrent work in the auditor, and extend `AuditReport` with explicit coverage and provenance data. MCP-specific path policy stays in the MCP adapter and does not change direct CLI behavior.

**Tech Stack:** Python 3.10+, `unittest`, pathlib/subprocess, TypeSafe SDK, MCP SDK, PowerShell project verification.

**Spec:** Current audit findings supplied in the task; project behavior and ownership are recorded in `project/docs/SPEC.md` and `project/docs/CURRENT_STATE.md`.

This pass also closes the related Runtime auto-enable and clean CLI no-op API-key
findings. Cost totals, launcher encoding, PyPI packaging, and diff-aware
regression scoring remain separately documented follow-up work.

## Global Constraints

- Bundled profile names must resolve only to repository-bundled profiles; custom profiles require an explicit JSON path.
- A Git metadata directory that cannot be inspected must fail closed instead of silently switching to an unrestricted directory walk.
- `--changed-only` must never report a clear no-op when only symlink or submodule changes are present.
- Provider response validation must fail closed for missing, non-finite, out-of-range, or non-normalized probabilities.
- Existing CLI, MCP, Runtime, and report consumers remain compatible unless the new fields are additive.
- `.kinotch/**` and common Base files remain read-only; Project-owned legacy paths declared in `project/project.json` remain editable.

## Review Focus

- A repository file named `development` or `development.json` must not shadow the bundled development profile.
- A broken or inaccessible `.git` must not cause ignored files to be sent to Jev.
- A changed symlink or gitlink must be visible as skipped/unknown information.
- A failed batch must stop pending work and avoid submitting all remaining batches.
- A syntactically shaped but semantically invalid Jev response must never become GREEN.

### Task 1: Profile and Git scanner trust boundaries

**Files:**
- Modify: `jev_audit/profiles.py`
- Modify: `jev_audit/scanner.py`
- Test: `tests/test_profiles.py`, `tests/test_scanner.py`

- [x] Add failing tests for bundled profile precedence, explicit custom profile paths, Git metadata failure, and changed symlink/gitlink reporting.
- [x] Run the focused tests and confirm the expected failures.
- [x] Implement bundled-name-first profile resolution, explicit JSON path validation, Git metadata fail-closed behavior, and skip metadata for non-regular changed entries.
- [x] Run focused scanner/profile tests and the full suite.

### Task 2: Fail-fast bounded batch execution

**Files:**
- Modify: `jev_audit/auditor.py`
- Test: `tests/test_auditor.py`

- [x] Add a failing test showing that after one batch raises, no later batch is submitted beyond the bounded in-flight window.
- [x] Run the focused test and confirm it fails against eager submission.
- [x] Implement a bounded scheduler with cancellation on first failure while preserving deterministic batch ordering.
- [x] Run focused and full tests.

### Task 3: Jev semantic response validation

**Files:**
- Modify: `jev_audit/jev_gateway.py`
- Test: `tests/test_gateway.py`

- [x] Add failing tests for missing status keys, invalid choice, non-finite/out-of-range probabilities, non-normalized status probabilities, and invalid noul probabilities.
- [x] Run the focused tests and confirm the failures.
- [x] Implement fail-closed validation with clear provider-response errors before aggregation.
- [x] Run focused and full tests.

### Task 4: MCP scope and hard caps

**Files:**
- Modify: `jev_audit/mcp_server.py`, `jev_audit/auditor.py`
- Modify: `project/defaults.json` or project documentation if configuration is exposed
- Test: `tests/test_mcp_server.py`, `tests/test_auditor.py`

- [x] Add failing tests for a path outside the configured MCP root and excessive workers/file limits.
- [x] Run focused tests and confirm failures.
- [x] Add an environment-configurable allowed root with a safe default and enforce hard limits at the MCP boundary.
- [x] Run focused and full tests.

### Task 5: Coverage and provenance report fields

**Files:**
- Modify: `jev_audit/models.py`, `jev_audit/scanner.py`, `jev_audit/auditor.py`, `jev_audit/reporting.py`
- Test: `tests/test_auditor.py`, `tests/test_reporting.py`, `tests/test_scanner.py`
- Modify: `README.md`, `docs/USAGE_GUIDE.md`, `project/docs/CURRENT_STATE.md`

- [x] Add failing tests for truncated paths, skipped paths by reason, and reproducibility metadata.
- [x] Run focused tests and confirm failures.
- [x] Add additive coverage/provenance fields and render the most useful summary without changing existing status semantics.
- [x] Run focused and full tests.

### Task 6: Security and remaining boundary documentation

**Files:**
- Modify: `README.md`, `docs/USAGE_GUIDE.md`, `project/docs/SPEC.md`

- [x] Document DEBUG body logging, MCP allowed-root behavior, response validation, and the known regression-risk diff limitation.
- [x] Confirm documentation matches the implemented defaults and run `git diff --check`.

## Verification Gate

- [x] `python -m unittest discover -s tests -v`
- [x] `python -c "import mcp, typesafe_sdk, jev_audit.mcp_server"`
- [x] `.\.kinotch\scripts\knt.ps1 doctor`
- [x] `.\.kinotch\scripts\knt.ps1 base-check`
- [x] `.\.kinotch\scripts\knt.ps1 verify`
- [ ] Commit, push, and confirm the latest GitHub Actions workflows for the pushed SHA.
