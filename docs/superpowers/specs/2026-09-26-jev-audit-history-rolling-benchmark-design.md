# Jev Audit lightweight history + rolling benchmark design

Status: **design proposed / user-approved concept / implementation not started**

Related:
- `jev-audit#7`
- `devflow#63`
- `devflow#64`
- `devflow#65`–`#70`

Audit base: `8c62774127f6bd7a945ed875bc682c498534f0c8`

## 1. Purpose

Add a deliberately small chronological history to Local Jev Audit and attach a rolling benchmark signal to each completed audit without turning `jev-audit` into an evaluation platform.

The feature exists to answer two practical questions:

1. What did recent audits look like over time?
2. Is the Jev decision path still behaving roughly as expected on a small fixed synthetic benchmark?

It is **not** intended to prove correctness, provide calendar analytics, rank repositories, or retain audited source.

## 2. Required behavior

### R-HIST-001 — one chronological record per completed audit

A completed Local CLI or Local STDIO MCP audit appends exactly one compact JSON object as one line to the user-level history file.

Default path:

```text
~/.jev-audit/history.jsonl
```

The history location is outside the audited repository. Repository source trees must not acquire user history files as a normal side effect.

### R-HIST-002 — existing report persistence stays separate

Existing CLI `--save` continues to mean “write this full AuditReport to the requested file”.

Automatic chronological history is a separate compact record and must not replace or silently alter `--save` output.

### R-HIST-003 — surfaces

History records distinguish:

- `cli`
- `local_mcp`

CLI and MCP must use the same record builder, benchmark engine, rolling-window logic, and writer rather than duplicating the contract.

### R-HIST-004 — no source retention

Automatic history must not contain:

- file content;
- diff content;
- raw provider request/response bodies;
- API keys or environment secret values;
- arbitrary scanned path contents;
- bundled benchmark fixture bodies.

File names/paths from the audited repository are also omitted from the compact history record. Full AuditReport remains available through existing explicit output/save paths when the caller intentionally requests it.

## 3. History record contract

Schema version starts at `1`.

Representative record:

```json
{
  "schema_version": 1,
  "timestamp": "2026-09-26T04:00:00.000Z",
  "surface": "cli",
  "profile": "development",
  "status": "review",
  "risk": 0.63,
  "files_scanned": 12,
  "batches": 3,
  "wall_clock_ms": 842.4,
  "model": "jev-1.13.0",
  "tool_version": "0.2.12",
  "git_head_sha": "...",
  "usage": {
    "input_tokens": 4210,
    "output_tokens": 320,
    "input_tokens_complete": true,
    "output_tokens_complete": true
  },
  "benchmark": {
    "fixture_id": "spec-mismatch",
    "score": 100,
    "error": null,
    "recent_scores": [100, 100, 0, 100],
    "recent_mean": 75.0
  }
}
```

### Field rules

- `timestamp`: UTC RFC3339/ISO-8601 string generated when the history record is finalized.
- `surface`: `cli` or `local_mcp`.
- `profile`: effective audit profile name. For custom profile paths, record the resolved profile name, not the custom file contents/path.
- `status`: existing audit overall status.
- `risk`: existing aggregate overall risk.
- `files_scanned`, `batches`, `wall_clock_ms`: copied from existing report/aggregate values.
- `model`: resolved model used by the real audit when a provider call occurred; retain existing `unknown`/provenance semantics for no-provider cases rather than inventing a model run.
- `tool_version`: current `jev_audit.__version__`.
- `git_head_sha`: existing provenance value or `null`; no repository path is stored.
- `usage`: compact copy of aggregate usage/completeness only.
- `benchmark`: always present so history consumers have a stable shape.

## 4. Benchmark contract

### R-BENCH-001 — fixed synthetic fixtures

Use a small fixed synthetic fixture set, target eight cases:

1. `clear-code` — benign implementation expected to remain non-actionable.
2. `concrete-issue` — obvious implementation defect expected to surface concrete risk.
3. `spec-mismatch` — explicit spec/implementation contradiction.
4. `regression-risk` — change context with a direct regression hazard.
5. `insufficient-context` — intentionally underdetermined input expected to preserve uncertainty rather than invent a violation.
6. `strong-rework` — obvious high-confidence defect expected to satisfy the rework contract.
7. `benign-config-docs` — harmless configuration/documentation pair expected to remain non-actionable.
8. `mild-review` — plausible review-level concern that should not require strong rework.

Fixtures are hand-authored, repository-independent, and small. They never include source copied from a real audited repository.

### R-BENCH-002 — one fixture per provider-backed audit

Do not run the full fixture suite for every audit.

For each real audit that actually issued at least one Jev provider request, select one fixture in round-robin order and issue at most one additional small benchmark provider call.

A Local clean `--changed-only` no-op that issued no Jev request remains provider-call-free:

- no benchmark provider call;
- benchmark `fixture_id = null`;
- benchmark `score = null`;
- rolling history is still appended.

### R-BENCH-003 — benchmark profile/model isolation

The benchmark contract is fixed and must not change merely because the caller selected a custom audit profile.

- fixture questions/expectations use a dedicated fixed benchmark contract;
- the benchmark uses the same resolved Jev model as the real audit for that run;
- caller profile changes affect the real audit but do not redefine benchmark expected outcomes.

### R-BENCH-004 — scoring

Each fixture has a deterministic predicate over the benchmark result.

- expected outcome satisfied: `100`;
- expected outcome not satisfied: `0`;
- benchmark/provider execution failed: `null`.

No weighted rubric is introduced in this feature.

### R-BENCH-005 — rolling window

Each history record embeds the most recent **up to 10 benchmark observations**, including the current observation when a fixture was attempted.

- numeric observations are `100` or `0`;
- failed benchmark observations remain visible as `null`;
- `recent_mean` is computed over numeric observations only;
- if there are no numeric observations, `recent_mean = null`;
- early history naturally contains fewer than 10 observations.

The history is not aggregated by date, repository, profile, or any other calendar/grouping dimension.

## 5. State ownership and lifetime

### Chronological history

Owner: user-level history file.

Lifetime: persistent until the user deletes it externally. This feature does not add rotation, retention limits, archival, compaction, or upload.

Mutation: append one line after each completed audit.

### Benchmark rotation/window

Primary source: the recent history tail.

The implementation should reconstruct next fixture index and rolling benchmark observations from the history tail where practical instead of introducing a second persistent state file.

If history is absent/corrupt/truncated:

- start a new benchmark sequence safely;
- do not fail the real audit;
- ignore malformed lines while reading a bounded tail when possible;
- never rewrite old history automatically merely to repair it.

## 6. Concurrency model

This is observability state, not correctness state.

Multiple concurrent CLI/MCP processes may select the same next fixture or observe a slightly stale rolling window. Strong distributed/process serialization is explicitly out of scope.

Requirements:

- each writer emits one complete JSONL line per write attempt;
- history corruption from the implementation itself should be avoided with a single serialized line write;
- duplicate round-robin fixture selection under concurrency is acceptable;
- audit correctness/status/exit behavior must not depend on benchmark ordering.

If real usage later demonstrates harmful concurrency drift, that is the evidence required to introduce stronger locking/state management.

## 7. Failure behavior

### Real audit fails

Preserve current audit failure behavior. Do not fabricate a successful history record for an audit that never produced an AuditReport.

### Benchmark fails after real audit succeeds

The real audit remains successful.

History record:

```json
{
  "benchmark": {
    "fixture_id": "...",
    "score": null,
    "error": "provider_error",
    "recent_scores": [..., null],
    "recent_mean": 80.0
  }
}
```

`error` must be a bounded stable classification, not raw provider text.

### History append fails

Do not change the audit status/risk/result.

CLI/MCP may expose a bounded non-secret warning through the normal diagnostic channel, but history persistence failure does not convert the audit to `review`/`rework` or alter provider results.

## 8. Compatibility

Must remain true:

- existing CLI flags retain meaning;
- `--save` full-report output is unchanged;
- `--json` AuditReport output is unchanged;
- `--fail-on` exit semantics are unchanged;
- MCP `audit_directory` returns the existing AuditReport schema and is not expanded with the history tail;
- clean changed-only no-op remains usable without `TYPESAFE_API_KEY`;
- existing profile/model/guardrail semantics remain unchanged.

## 9. Suggested implementation boundaries

The exact names are implementation detail, but responsibilities should remain separate:

- benchmark fixture definitions + score predicates;
- history record projection from AuditReport;
- bounded history-tail reader / rolling window calculator;
- JSONL append writer;
- post-audit orchestrator shared by CLI/MCP.

Do not put persistence/benchmark logic into scanner or aggregate semantics.

## 10. Verification requirements

TDD/regression coverage must include at least:

1. JSONL append produces one compact record and excludes source/diff/path contents.
2. Existing full `--save` report remains unchanged.
3. CLI surface is recorded as `cli`.
4. MCP surface is recorded as `local_mcp`.
5. Fixture selection rotates deterministically in serial use.
6. Rolling window caps at 10 observations.
7. `null` remains in `recent_scores` but not in `recent_mean` denominator.
8. Benchmark mismatch scores `0`; match scores `100`.
9. Benchmark provider failure becomes `null` without failing the real audit.
10. Clean changed-only no-op makes no benchmark/provider call and still writes history.
11. Malformed/absent history does not fail the audit.
12. History-write failure does not change audit status/exit semantics.
13. Custom audit profile does not redefine fixed benchmark expectations.
14. Existing test matrix / optional integrations / Windows launcher / Verify remain green.

## 11. Non-goals

- dashboard or charts;
- daily/weekly/monthly aggregation;
- central service/database;
- history upload/sync;
- repository scoring/ranking;
- full benchmark suite on every audit;
- statistical confidence calculations;
- history retention policy;
- source/diff retention;
- automatic remediation from benchmark score.

## 12. Completion boundary

Repository implementation is complete only when:

- Issue `jev-audit#7` acceptance is satisfied;
- tests/Verify pass on the implementation PR;
- user-facing docs and Current State are reconciled;
- changed-scope review finds no privacy/result-contract regression.

This Local implementation does not itself deploy or modify `kinotch-api` Production.