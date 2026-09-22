# KiNoTch Runtime Pilot — Current State

Status: live CLI/MCP comparison complete; Contract evaluation pending

## Current implementation

- `jev_audit/runtime_bridge.py` is an optional 83-line boundary.
- CLI and MCP import the same `run_audit` bridge entry point.
- Without the `pilot` extra, the bridge calls the existing Audit Core directly.
- With the pinned `kinotch-runtime` package installed, the bridge registers and
  executes `repo.audit` through the Runtime `ActionRegistry`.
- The Audit Core, scanner, batching, gateway, aggregation, and existing MCP
  path resolution were not changed.

## Evidence

- Existing jev-audit suite: 35 tests passed without Runtime installed.
- Full suite with the Runtime source available: 37 tests passed; the actual
  Runtime bridge and expected-error tests executed.
- Runtime repository Contract suite: 18 tests passed.
- Direct CLI live run: 14 files, 2 batches, `review`, exit 0.
- Runtime CLI live run: 14 files, 2 batches, `review`, exit 0.
- Runtime MCP live call: `CallToolResult`, `isError=false`, 14 files, 2
  batches, `review`.
- Invalid profile: both paths exit 2; Runtime preserves `NOT_FOUND`.

## Next controlled check

The next decision is whether the live evidence demonstrates reduced shared
responsibility rather than merely adding a wrapper. Compare configuration
mapping, dependency/install cost, adapter complexity, and repeated change
reasons. Keep credentials out of source, logs, fixtures, and report artifacts.
A single GREEN result is not an audit-quality proof.

If the Runtime path increases wrappers or configuration without reducing
shared responsibility, stop the Pilot and revise the Contract instead of
adding a Surface Pack.
