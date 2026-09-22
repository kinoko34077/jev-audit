# KiNoTch Runtime Pilot — Current State

Status: bridge preparation complete; live Jev validation pending

## Current implementation

- `jev_audit/runtime_bridge.py` is an optional 65-line boundary.
- CLI and MCP import the same `run_audit` bridge entry point.
- Without the `pilot` extra, the bridge calls the existing Audit Core directly.
- With the pinned `kinotch-runtime` package installed, the bridge registers and
  executes `repo.audit` through the Runtime `ActionRegistry`.
- The Audit Core, scanner, batching, gateway, aggregation, and existing MCP
  path resolution were not changed.

## Evidence

- Existing jev-audit suite: 35 tests passed without Runtime installed.
- Full suite with the Runtime source available: 36 tests passed; the actual
  Runtime bridge test executed without an external Jev request.
- Runtime repository Contract suite: 18 tests passed.
- No live source upload or TypeSafe API request was performed in this
  preparation phase.

## Next controlled check

An operator-authorized live check should compare the direct and Runtime paths
for CLI JSON output, exit codes, structured errors, MCP return behavior,
configuration mapping, dependency/install cost, and adapter complexity. Keep
credentials out of source, logs, fixtures, and report artifacts. A single
GREEN result is not an audit-quality proof.

If the Runtime path increases wrappers or configuration without reducing
shared responsibility, stop the Pilot and revise the Contract instead of
adding a Surface Pack.
