# KiNoTch Runtime Pilot — Current State

Status: evaluation complete; Runtime remains optional and provisional

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

## Evaluation

### What worked

- Audit Core, scanner, batching, gateway, aggregation, and MCP path resolution
  remained unchanged.
- CLI and MCP use the same localized bridge, while the default installation
  keeps the direct legacy path.
- Expected input, no-auditable-file, and known provider failures retain exit
  code 2 and receive structured Runtime codes with the original message at the
  bridge boundary. Truly unexpected Runtime failures remain redacted by the
  Runtime kernel as `INTERNAL_ERROR`.

### What did not reduce complexity

- CLI and MCP already shared Audit Core before the Pilot, so Runtime did not
  create that reuse.
- `ActionResult` is currently a transparent in-process wrapper around the
  domain `AuditReport`; it is unwrapped before existing CLI/MCP presentation.
- Runtime Config, Progress, Cancellation, Resource, Artifact, and Logging were
  not needed by the audit path.
- The optional Git dependency and bridge add a layer, but this one-repo Pilot
  provides no measured maintenance reduction.

### Contract decision

The next Pilot may carry only the limited Action/Request/Error meanings after
the Runtime-side maturity review. No Surface Pack or required Runtime
dependency is added here. The Python Runtime remains optional.

## Next controlled check

The next decision is whether a heterogeneous repository demonstrates reduced
shared responsibility rather than merely adding a wrapper. Keep credentials
out of source, logs, fixtures, and report artifacts. A single GREEN result is
not an audit-quality proof.

If the Runtime path increases wrappers or configuration without reducing
shared responsibility, stop the Pilot and revise the Contract instead of
adding a Surface Pack.
