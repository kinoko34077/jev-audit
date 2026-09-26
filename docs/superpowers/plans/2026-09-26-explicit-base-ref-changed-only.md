# Jev Audit Explicit Base-Ref Changed-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `base_ref` comparison mode to existing `--changed-only` so a checked-out head commit can be audited against an arbitrary base commit without falsifying Jev Git provenance.

**Architecture:** Keep current changed-only behavior unchanged when no base is supplied. When `base_ref` is supplied, resolve it to an exact commit, compute candidate paths and bounded hunks from `base_ref` to the current `HEAD`, audit the current HEAD file contents, and report both exact base/head SHAs. The bridge in `kinoko34077/testapp` then checks out the requested head and calls the existing Jev CLI with `--changed-only --base-ref <resolved-base-sha>`.

**Tech Stack:** Python 3.10+, existing jev-audit scanner/auditor/CLI, unittest/pytest-compatible existing test suite, Git.

**Spec:** `kinoko34077/testapp@5ebf4729c40249ad871f1d12d6ecd87ba0a7bc4f:docs/superpowers/specs/2026-09-26-chatgpt-tool-bridge-design.md`; owning local requirement: `jev-audit#9`.

## Global Constraints

- Existing `jev-audit . --changed-only` semantics remain unchanged when `base_ref` is omitted.
- `base_ref` is valid only with `changed_only=True`; otherwise raise `ValueError` before provider work.
- Resolve `base_ref` with Git to an exact commit SHA before candidate enumeration/provider work.
- Candidate paths for explicit-base mode come from `git diff --name-only <base_sha> HEAD --` plus existing safety/exclusion handling.
- Change hunks for explicit-base mode come from `git diff <base_sha> HEAD -- <paths>` with existing `--no-ext-diff --no-textconv` protections and existing truncation limits.
- Current file content is always read from the checked-out current `HEAD`, not from the base commit.
- Deleted paths relative to base remain represented as deleted changes; they are not silently treated as clear.
- `scan.git.head_sha` remains the actual current HEAD SHA.
- Explicit-base mode adds exact base SHA as Git/provenance metadata; it must never overwrite head SHA.
- Clean base→head diff remains provider-call-free and returns the existing clear no-op semantics.
- Existing sensitive/binary/generated/symlink/gitlink handling remains unchanged.
- Existing model/profile/threshold/batching semantics remain unchanged.
- No arbitrary shell is introduced; all Git invocations continue through `_run_git` argument arrays.
- Production code follows RED → verify RED → GREEN → verify GREEN → refactor.

## Review Focus

- `base_ref` resolves to the same commit as HEAD: clean no-op, zero provider calls, exact equal base/head provenance.
- Base has a file modified in HEAD: scan includes current HEAD content plus base→head bounded diff.
- File deleted between base and HEAD: path appears in deleted metadata and does not yield false clear when it is the only change.
- Invalid/missing/non-commit base ref: deterministic input error before provider work.
- Existing local working-tree `--changed-only` with no `base_ref`: behavior and provenance remain byte-for-byte compatible where practical.

---

### Task 1: Scanner explicit-base candidate selection

**Files:**
- Modify: `jev_audit/scanner.py`
- Modify: `tests/test_scanner.py`

**Interfaces:**
- Extend `ScanOptions` with `base_ref: str | None = None`.
- Explicit-base scanning resolves `base_ref` to `base_sha` and returns it in `ScanResult.git` metadata alongside current `head_sha`.

- [ ] **Step 1: Write failing scanner tests**

Add tests for: base→HEAD modified file uses HEAD content; new file; deleted file; clean equal base/head; invalid base; base-ref rejected when not changed-only; existing no-base changed-only remains unchanged. Assert Git calls retain `--no-ext-diff --no-textconv`.

- [ ] **Step 2: Run targeted tests and verify RED**

Run: `python -m pytest tests/test_scanner.py -q`

Expected: FAIL because `ScanOptions` has no `base_ref` behavior.

- [ ] **Step 3: Implement minimal scanner support**

Add a helper that resolves the base commit with `git rev-parse --verify <base_ref>^{commit}`. In explicit-base changed-only mode, use exact `base_sha` and current `HEAD` for name/diff enumeration, while reading files from the current checkout. Preserve current working-tree changed-only branch when `base_ref is None`.

- [ ] **Step 4: Run targeted and full tests**

Run: `python -m pytest tests/test_scanner.py -q`

Then: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: scan changed files from explicit base ref`

### Task 2: Audit-core provenance and option plumbing

**Files:**
- Modify: `jev_audit/auditor.py`
- Modify: `tests/test_auditor.py`
- Modify if required by existing report assertions: `tests/test_reporting.py`

**Interfaces:**
- Extend `audit_directory(..., changed_only: bool = False, base_ref: str | None = None, ...)`.
- Pass `base_ref` into `ScanOptions`.
- Add resolved `git_base_sha` (or equivalently named exact field consistent with existing provenance style) while retaining `git_head_sha`.

- [ ] **Step 1: Write failing audit/provenance tests**

Assert `base_ref` without changed-only raises `ValueError`; explicit-base report contains exact base/head; equal base/head no-op keeps zero batches/provider work; current no-base reports retain old fields/values.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_auditor.py tests/test_reporting.py -q`

Expected: FAIL because audit core does not accept/record base ref.

- [ ] **Step 3: Implement minimal option/provenance plumbing**

Validate option relationship before provider work, pass through scanner, and add base SHA to provenance from scanner metadata. Do not change aggregation or thresholds.

- [ ] **Step 4: Verify GREEN and full suite**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: report explicit changed-only base provenance`

### Task 3: CLI surface

**Files:**
- Modify: `jev_audit/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- New option: `--base-ref <ref>`.
- CLI passes `base_ref=args.base_ref` to `run_audit`.
- Existing exit-code semantics remain unchanged.

- [ ] **Step 1: Write failing CLI tests**

Assert parser/dispatch accepts `--changed-only --base-ref <sha>` and passes exact value; `--base-ref` without `--changed-only` exits through existing error handling as invalid input; `--json --fail-on never` remains usable for the bridge.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_cli.py -q`

Expected: FAIL because CLI has no `--base-ref`.

- [ ] **Step 3: Implement minimal CLI option**

Add only the one new argument and plumbing. Do not add general range syntax, arbitrary revsets, or model behavior changes.

- [ ] **Step 4: Verify GREEN and full suite**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add changed-only base-ref cli option`

### Task 4: Documentation and regression verification

**Files:**
- Modify: `README.md`
- Modify: `docs/USAGE_GUIDE.md`
- Modify if appropriate: `docs/ARCHITECTURE.md`

**Interfaces:**
- Document local-worktree mode vs explicit base→HEAD mode distinctly.
- Bridge-oriented example: `jev-audit . --changed-only --base-ref <base-sha> --json --fail-on never`.

- [ ] **Step 1: Add/extend documentation regression assertion if the project has documentation tests; otherwise add a focused test in `tests/test_cli.py` for help text**

The assertion must prove `--base-ref` is discoverable and explicitly requires changed-only.

- [ ] **Step 2: Verify RED before docs/help implementation where applicable**

Run the owning targeted test and confirm expected failure.

- [ ] **Step 3: Update docs/help text**

Explain that current HEAD remains the audited content/provenance head and `base_ref` only selects the comparison base. State clean equal-base/head remains provider-free.

- [ ] **Step 4: Run complete verification**

Run: `python -m pytest -q`

Then run repository Verify according to current project workflow (`./.kinotch/scripts/knt.ps1 verify` on supported shell/CI).

Expected: all checks PASS.

- [ ] **Step 5: Commit**

Commit message: `docs: explain explicit base-ref audits`

### Task 5: PR and bridge handoff

**Files:**
- No additional production files unless a verification defect is reproduced by a failing test first.
- Update `jev-audit#9` with exact verification evidence.

**Interfaces:**
- The bridge may pin the accepted Jev commit/release and invoke `jev-audit . --changed-only --base-ref <resolved-base-sha> --json --fail-on never`.

- [ ] **Step 1: Open a dedicated PR referencing `jev-audit#9`**

Record base SHA, implementation head, test commands, and exact changed-only provenance evidence.

- [ ] **Step 2: Run GitHub Actions/Verify and inspect failures**

All existing Local CLI/MCP behavior must remain green.

- [ ] **Step 3: Re-audit changed scope and review compatibility**

Confirm no behavior change to normal `--changed-only` when base-ref is absent.

- [ ] **Step 4: Merge only after verification**

After merge, record the exact accepted commit for `testapp` to pin. Release/tag publication is separate and not required unless current repository policy makes it necessary.
