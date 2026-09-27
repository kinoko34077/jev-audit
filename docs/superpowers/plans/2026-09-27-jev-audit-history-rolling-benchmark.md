# Jev Audit Local history + rolling benchmark implementation plan

Status: implemented and repository-verified

Owning work: `jev-audit#7`, parent `devflow#63`
Base: latest accepted `main` (`e05481517eb05c39112b092d03fd883951f2b97f`)
Design: `docs/superpowers/specs/2026-09-26-jev-audit-history-rolling-benchmark-design.md`

## Goal

Implement the approved user-level JSONL history and one-fixture rolling benchmark without changing AuditReport, CLI output/exit semantics, MCP response schema, scan/aggregation semantics, or clean changed-only provider-free behavior.

## Task 1 — history contract and bounded storage

Files:
- add `jev_audit/history.py`
- add `tests/test_history.py`

TDD:
1. RED for compact record projection, source/path/secret exclusion, rolling max 10, null-preserving numeric mean, malformed/absent tail, and one-line append.
2. Implement default `~/.jev-audit/history.jsonl`, bounded tail parsing, record projection, and append writer.
3. Keep history failures typed/bounded and never expose file contents.
## Task 2 — fixed benchmark engine

Files:
- add `jev_audit/benchmark.py`
- add `tests/test_benchmark.py`

TDD:
1. RED for eight fixed fixture IDs, deterministic round-robin selection from history, 100/0/null scoring, fixed benchmark profile semantics, and provider-failure isolation.
2. Reuse the existing `audit_with_jev` provider/response validation path with the real audit's resolved model.
3. Execute exactly one small synthetic fixture only when `report.batches > 0`; no benchmark call for clean no-op reports.

## Task 3 — shared post-audit orchestration

Files:
- add `jev_audit/observability.py`
- modify `jev_audit/cli.py`
- modify `jev_audit/mcp_server.py`
- add/update CLI/MCP regression tests

TDD:
1. RED that CLI records `surface=cli`, MCP records `surface=local_mcp`, and both preserve existing returned/output AuditReport data.
2. Run benchmark best-effort, derive rolling state from bounded history tail, then append one record.
3. Benchmark or history failure must not change audit status, CLI fail-on exit code, MCP response, or full `--save` output.
## Task 4 — compatibility and docs

Files:
- update `README.md` / `docs/USAGE_GUIDE.md` only where user-facing behavior needs documenting
- update `project/docs/CURRENT_STATE.md`
- update approved design status to implemented after verification

Verification:
- focused new tests
- full `python -m unittest discover -s tests -v`
- `git diff --check`
- `knt verify` / GitHub `Tests` + `Verify`
- changed-scope privacy review

## Completion

Open a dedicated PR for `jev-audit#7`. Merge only after tests/Verify and changed-scope review succeed. No release/deploy is part of this Local work.