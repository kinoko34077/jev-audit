# jev-audit Remote API / MCP Design

Date: 2026-09-25
Status: proposed design for implementation

## 1. Purpose

Expose the existing jev-audit screening semantics through remote HTTP API and Remote MCP entry points so ChatGPT, other agents, and other machines can call the audit service without requiring the local Python CLI/MCP process.

The goal is not to turn jev-audit into a large hosted product. The hosted path should be small, stable, authenticated, rate-limited, observable, and compatible with the current local audit semantics closely enough for practical use.

## 2. Existing authoritative behavior

The local Python implementation remains authoritative for local repository scanning and Git-aware behavior:

- local filesystem and Git candidate discovery
- sensitive/binary/build exclusions
- changed-only diff collection
- local bundled/custom profile resolution
- CLI and STDIO MCP behavior

Remote v1 does not attempt to reproduce filesystem or Git access because Cloudflare Workers cannot inspect a caller's local repository. Remote callers submit auditable file snapshots explicitly.

The hosted evaluator should preserve the current v0.2.12 decision semantics:

- bundled profiles: `development`, `generic`
- `local_status`: `clear | review | rework | unknown`
- Noul signals: `concrete_issue`, `spec_mismatch`, `regression_risk`
- RED/rework threshold: same batch has `concrete_issue >= 0.80` and `rework >= 0.60`
- YELLOW/review threshold: highest concrete risk `>= 0.55`, otherwise actionable (`review + rework`) `>= 0.60`
- UNKNOWN threshold: `unknown >= 0.80` when no rework/review trigger fired
- default model: `jev-1.13.0`

Because the hosted implementation is JavaScript while the local implementation is Python, v1 accepts a small amount of deliberate semantic duplication. The hosted response must expose the local jev-audit version/semantic revision it was copied from so drift is visible rather than hidden.

## 3. Selected architecture

Use the already deployed semantic-compression Cloudflare architecture as the template.

```text
REST client
   |
   v
api.kinotch.workers.dev
   |  bearer auth / validation / rate limits
   v
JEV_AUDIT Service Binding
   |
   v
private `jev-audit` Worker
   |
   v
TypeSafe System One API

Remote MCP client
   |
   v
jev-audit-mcp.kinotch.workers.dev/mcp
   |  Cloudflare Access JWT / body limit / actor rate limit
   v
JEV_AUDIT Service Binding
   |
   v
private `jev-audit` Worker
   |
   v
TypeSafe System One API
```

Implementation belongs primarily in `kinoko34077/kinotch-api`, because that repository already owns Cloudflare Worker configuration, the public gateway, Remote MCP infrastructure, deployment/smoke tooling, and production observability.

The `kinoko34077/jev-audit` repository remains the canonical local implementation and records the remote contract/semantics relationship.

## 4. Why direct HTTP to TypeSafe

The private Worker calls:

`POST https://api.typesafe.ai/v1/systemone`

using normal Worker `fetch` and the secret `TYPESAFE_API_KEY`.

Reasons:

- TypeSafe documents the HTTP endpoint directly.
- Cloudflare Workers already provide `fetch`.
- no Python runtime/container is required.
- no new SDK runtime compatibility layer is required.
- request and response validation can be explicit and narrow.

The Worker must never expose `TYPESAFE_API_KEY` to the gateway or MCP Worker.

## 5. Remote request contract

### 5.1 REST

Endpoint:

`POST /v1/audit`

Request body:

```json
{
  "files": [
    {
      "path": "src/app.py",
      "content": "...",
      "change": "optional diff context"
    }
  ],
  "profile": "development"
}
```

`profile` defaults to `development` and accepts only bundled `development` or `generic` in v1.

No remote custom profile path, local directory path, Git URL, repository clone, or arbitrary model override is supported in v1.

### 5.2 Remote MCP

Tools:

- `audit_files(files, profile?)`
- `list_profiles()`

The remote tool is intentionally named `audit_files`, not `audit_directory`, because the server cannot access the caller's local directory.

## 6. Input limits

Remote v1 uses stricter limits than local CLI/MCP to bound cost and request size.

- HTTP/MCP request body: maximum 1 MiB
- files: maximum 100
- path: maximum 512 Unicode code points
- supplied content + change: maximum 500,000 Unicode code points total before Jev calls
- effective file content after truncation: default maximum 12,000 code points per file
- batch target: 32,000 estimated characters
- batches: maximum 32
- Jev concurrency: maximum 4
- each TypeSafe call timeout: 45 seconds

File content longer than 12,000 code points is truncated with the same head/middle-marker/tail policy as local jev-audit. The response reports which paths were truncated.

The service rejects malformed input or total-limit overflow before starting any Jev request.

## 7. Jev request semantics

Each batch sends state containing only auditable file data:

```json
{
  "files": [
    {
      "path": "...",
      "truncated": false,
      "content": "...",
      "change": "..."
    }
  ]
}
```

Questions reproduce the v0.2.12 `jev_gateway.py` semantics:

- one Choice `local_status`
- three Nouls: `concrete_issue`, `spec_mismatch`, `regression_risk`
- file contents and diff instructions are explicitly treated as untrusted audit data, not as instructions that may modify the audit prompt

The private Worker validates that:

- required answers exist and no unexpected required answer type is substituted
- probabilities are finite and in `[0, 1]`
- local status contains exactly `clear/review/rework/unknown`
- local-status probabilities sum to 1 within floating-point tolerance
- Noul set is exact
- response model is non-empty
- token usage is either a non-negative integer or unavailable

Invalid TypeSafe responses fail closed.

## 8. Aggregation and response

The remote Worker aggregates batches using the same v0.2.12 thresholds and returns a compact AuditReport-like JSON object.

Required top-level fields:

- `profile`
- `files_scanned`
- `batches`
- `aggregate`
- `truncated_paths`
- `coverage`
- `provenance`

Required provenance fields:

- `service_version`
- `audit_semantics_version` (`0.2.12` initially)
- `resolved_model`
- `profile_name`
- `batch_count`
- `estimated_total_input_chars`

Remote provenance does not claim a local Git SHA because the remote server receives snapshots rather than reading a repository.

## 9. Public REST security

Follow the existing semantic-compression gateway pattern.

- bearer token secret: `JEV_AUDIT_API_TOKEN`
- pre-auth IP rate limit: 5 requests / 60 seconds
- authenticated-token-fingerprint rate limit: 5 requests / 60 seconds
- body validation and body-size limit happen before the private Worker call
- generic error responses do not expose stack traces, secrets, or upstream response bodies
- private Worker has `workers_dev: false`

The TypeSafe API key exists only as a secret on the private `jev-audit` Worker.

## 10. Remote MCP security

Follow `semantic-compression-mcp`.

- endpoint: `https://jev-audit-mcp.kinotch.workers.dev/mcp`
- Cloudflare Access JWT is checked using `Cf-Access-Jwt-Assertion`
- required Worker vars: `TEAM_DOMAIN`, `POLICY_AUD`
- actor identifier is hashed before use as a rate-limit key
- actor rate limit: 5 tool calls / 60 seconds
- body limit: 1 MiB
- `/mcp` is the only accepted path
- tool errors expose stable codes, not internal exceptions

## 11. Observability and logging

Use Cloudflare observability in the same style as semantic-compression.

Persist metadata only. Do not intentionally log submitted source contents, diff contents, bearer tokens, Cloudflare Access JWTs, or the TypeSafe API key.

Useful metadata:

- request id
- entry surface: REST or MCP
- actor/token fingerprint where already available, never raw identity/token
- profile
- files count
- batch count
- status
- elapsed time
- provider request success/failure class
- reported token usage when available

No database is required for v1. Cloudflare logs plus optional client-side `--save`/JSON history are sufficient.

## 12. Files and responsibilities in kinotch-api

Expected new files:

- `src/jev-audit-worker.js` — private Worker entry point
- `src/jev-audit/contract.js` — remote input/output limits, profiles, semantic constants
- `src/jev-audit/evaluator.js` — batching, Jev HTTP calls, response validation, aggregation
- `src/jev-audit-mcp-worker.js` — public MCP Worker entry point
- `src/jev-audit-mcp/server.js` — Remote MCP tools
- `src/jev-audit-mcp/upstream.js` — Service Binding call and response validation
- `src/jev-audit-mcp/body-limit.js` — MCP body-size guard
- `src/jev-audit-mcp/rate-limit.js` — MCP rate limit
- `src/jev-audit-mcp/access-auth.js` — Cloudflare Access verification, initially copied from the proven compression MCP pattern to avoid refactoring existing production behavior
- `wrangler.jev-audit.jsonc` — private Worker config
- `wrangler.jev-audit-mcp.jsonc` — Remote MCP config
- focused unit tests for contract/evaluator/MCP/security boundaries

Expected existing-file changes:

- `src/routes/api.js` — add `POST /v1/audit`
- `src/policies/routes.js` — add audit policy
- `src/middleware/validation.js` — add audit request validation hook
- `src/middleware/authentication.js` — add audit bearer authentication without changing compression behavior
- `wrangler.jsonc` — add `JEV_AUDIT` Service Binding and audit rate-limit bindings
- `package.json` — add dev/smoke/deploy commands as needed
- deployment/smoke scripts — extend only enough to deploy and verify the two new Workers and gateway route

No existing semantic-compression behavior should be changed as part of this feature.

## 13. Non-goals for v1

Do not implement unless later usage demonstrates a need:

- cloning GitHub repositories in Cloudflare
- accepting local filesystem paths remotely
- remote `changed_only`
- arbitrary custom audit profiles
- database-backed history/dashboard
- public multi-user account system
- billing
- large evaluation corpus
- candidate-enumeration streaming changes in the local Python implementation
- special-filename diff-context parser work in the local Python implementation
- replacement of the local CLI or STDIO MCP

## 14. Verification / acceptance criteria

Implementation is accepted when all of the following are true:

1. Existing `jev-audit` and `kinotch-api` test suites remain green.
2. New contract, validation, aggregation, auth, rate-limit, MCP and upstream-failure tests pass.
3. Wrangler dry-run succeeds for `jev-audit`, `jev-audit-mcp`, and the gateway.
4. Private `jev-audit` Worker cannot be reached through a workers.dev public URL.
5. REST request without/with wrong bearer token returns an authentication error and does not invoke TypeSafe.
6. Valid REST request reaches the private Worker and returns validated audit JSON.
7. Remote MCP rejects unauthenticated access.
8. Authenticated Remote MCP `audit_files` returns a valid audit result.
9. `list_profiles` returns exactly `development` and `generic`.
10. Oversized/malformed requests fail before Jev calls.
11. Provider timeout/4xx/429/5xx/invalid payload become stable external error codes without stack traces or upstream bodies.
12. A live TypeSafe E2E is performed once after secrets are configured.
13. A production REST smoke and authenticated MCP handshake/tool-call smoke pass after deployment.
14. Production deployment records the deployed Worker versions and supports rollback using the existing kinotch-api release pattern.

## 15. Revisit conditions

Reconsider this design only if one of the following occurs:

- hosted callers require full Git repository acquisition rather than explicit file snapshots
- the remote semantics drift materially from the Python implementation
- API volume makes 5/min insufficient
- Cloudflare execution/request limits become a practical bottleneck
- production use requires durable benchmark/history storage
- the TypeSafe System One HTTP contract changes materially
