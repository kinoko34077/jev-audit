# jev-audit Boundary Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the remaining profile, Runtime, report, Git path, launcher, and version boundaries without changing Audit Core thresholds or Jev questions.

**Architecture:** Keep profile resolution shared in `profiles.py`, keep MCP root and size policy in `mcp_server.py`, and keep Runtime opt-in behavior in `runtime_bridge.py`. Extend additive report metadata for effective execution and coverage while preserving existing aggregate fields and status semantics. Centralize NUL-delimited Git parsing in the scanner.

**Tech Stack:** Python 3.10+, `unittest`, `subprocess` Git integration, PowerShell launchers, GitHub Actions.

**Spec:** User-provided `jev-audit 残存境界・軽微問題 総仕上げ修正指示書` in the active task.

## Global Constraints

- Keep bundled profiles, fail-closed Git handling, bounded batch scheduling, MCP root caps, Runtime explicit opt-in, coverage/provenance, clean no-op, pinned model, `.kinotch/` exclusion, and Base/Project boundaries.
- Do not change GREEN/YELLOW/RED/UNKNOWN thresholds, Jev questions, default scan limits, secret exclusions, changed-only meaning, or make Runtime mandatory.
- Do not add credentials to source, tests, fixtures, logs, or CI.
- Bump project version from `0.2.9` to `0.2.10`; do not change Base version `0.3.8`.

## Review Focus

- A custom MCP profile outside the allowed root must be rejected before its bytes are read.
- Runtime opt-in without an installed or compatible Runtime must fail explicitly rather than use direct execution.
- A report must distinguish requested workers, effective workers, excluded directories, and incomplete provider token usage.
- Git names containing newlines must remain one path through full, changed-only, and staged enumeration.
- Generated global launchers must keep the Python path in the Unicode-capable PowerShell shim and preserve arguments and exit status.

### Task 1: Shared profile references and MCP profile guard

**Files:** `jev_audit/profiles.py`, `jev_audit/mcp_server.py`, `tests/test_profiles.py`, `tests/test_mcp_server.py`

- [x] Add failing tests for shared bundled/custom reference resolution, allowed-root custom profile reads, opt-out reads, no-read rejection, and MCP custom profile byte-size cap.
- [x] Run focused profile/MCP tests and confirm the new tests fail for the current implementation.
- [x] Add `resolve_profile_reference()` and `load_profile_from_reference()` in `profiles.py`; make `load_profile()` use them and preserve bundled-name precedence.
- [x] Make MCP validate resolved custom profile paths and file size before Core loading; keep bundled names unrestricted and allow outside paths only with `JEV_AUDIT_ALLOW_ANY_PATH=1`.
- [x] Run focused tests and the full suite.

### Task 2: Runtime explicit dependency failure

**Files:** `jev_audit/runtime_bridge.py`, `tests/test_runtime_bridge.py`, `README.md`, `docs/RUNTIME_PILOT.md`, `docs/USAGE_GUIDE.md`, `project/docs/CURRENT_STATE.md`

- [x] Add failing tests for opt-in missing Runtime and import-time internal dependency failure.
- [x] Run the focused Runtime tests and confirm red.
- [x] Raise a structured dependency error whenever explicit opt-in cannot load the Runtime; preserve direct execution only when opt-in is absent.
- [x] Synchronize docstrings and documentation with explicit opt-in plus installed dependency requirements.
- [x] Run focused tests and the full suite.

### Task 3: Report execution metadata and token completeness

**Files:** `jev_audit/models.py`, `jev_audit/auditor.py`, `jev_audit/aggregate.py`, `jev_audit/reporting.py`, `tests/test_auditor.py`, `tests/test_aggregate.py`, `tests/test_reporting.py`

- [x] Add failing tests for requested/effective workers, no-op effective zero, JSON persistence, and complete/partial/missing usage metadata.
- [x] Run focused tests and confirm red.
- [x] Add additive provenance fields and usage completeness/missing-batch counts without changing existing totals or thresholds.
- [x] Render incomplete token usage and excluded-directory metadata without implying repository-wide character coverage.
- [x] Run focused tests and the full suite.

### Task 4: Excluded-directory coverage accounting

**Files:** `jev_audit/scanner.py`, `jev_audit/models.py`, `jev_audit/auditor.py`, `jev_audit/reporting.py`, `tests/test_scanner.py`, `tests/test_auditor.py`, `tests/test_reporting.py`

- [x] Add failing tests for `.kinotch`, nested ignored directories, and omission of individual pruned files.
- [x] Run scanner/report tests and confirm red.
- [x] Record unique root-relative excluded directories while pruning, separate file-entry skips from directory exclusions, and keep character coverage scoped to scanned text files.
- [x] Run focused tests and the full suite.

### Task 5: NUL-safe Git path parsing

**Files:** `jev_audit/scanner.py`, `tests/test_scanner.py`

- [x] Add failing tests for newline filenames in full, changed-only, and staged parsing, while retaining non-ASCII path coverage.
- [x] Run focused scanner tests and confirm red.
- [x] Add one NUL parser helper and use `-z`/`--stage -z` for Git enumerations and diff name parsing.
- [x] Run focused tests and the full suite.

### Task 6: Launcher, documentation, and release metadata

**Files:** `install-command.ps1`, `.github/workflows/tests.yml`, `pyproject.toml`, `jev_audit/__init__.py`, `project/docs/CURRENT_STATE.md`, `README.md`, `docs/USAGE_GUIDE.md`, tests as needed

- [x] Add/update static launcher and version synchronization tests.
- [x] Implement only the remaining Unicode-safe launcher assertions and Windows smoke coverage needed by the specification.
- [x] Bump all project version sources to `0.2.10`, update current-state evidence, and synchronize user-facing boundary descriptions.
- [x] Run compile, import, PowerShell parse, wheel metadata, Base commands, full tests, and `git diff --check`.

### Task 7: Commit, push, and external verification

- [ ] Review the full diff against the user checklist and confirm forbidden thresholds/questions were not changed.
- [ ] Commit and push `main`.
- [ ] Confirm Python 3.10–3.14, optional integrations, Windows launcher, and Base Verify workflows succeed.
- [ ] Record that no live Jev API smoke was run unless safe credentials are explicitly available.
