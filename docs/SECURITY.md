# Security and trust model

## Intended deployment

A developer-controlled local host, a private state directory on local disk, native coding clients, and explicitly approved repositories. This is not an Internet-facing service, multi-tenant authorization system, remote execution sandbox, or independently security-audited product.

The package contains no model-provider client, API-key lookup, embeddings, telemetry or outbound network service. Its only core network transport is authenticated loopback HTTP and its local proxy. Tests or external analyzers can themselves access networks and credentials under the invoking user's permissions.

## Implemented controls

Indexing parses source without importing/executing the target application. Source paths are resolved and constrained to the configured root; external symlink targets are rejected/skipped. Static source windows verify content identity and enforce bounds. Unknown config fields, invalid query names, arbitrary SQL, arbitrary shell execution and remote roots are not MCP capabilities.

The HTTP server binds only `127.0.0.1`, validates Host and Origin, requires a local bearer secret, rejects duplicate sensitive headers and transfer-encoded bodies, limits request size, bounds request-thread concurrency and disables cacheable responses. It implements JSON HTTP responses rather than exposing an unauthenticated database endpoint. The stdio proxy uses the same secret from a file, not a command-line token string.

New private state/token files use restrictive POSIX permissions. Existing insecure token permissions are rejected. Windows ACL equivalence has not been audited; use an OS-protected user directory. Config generation prints fragments and does not modify global client settings or expose provider credentials.

Read tools are enabled by default. Static refresh and repository execution require separate service flags. Test/analyzer subprocesses additionally require a trust acknowledgement. They execute fixed argument arrays without shell interpolation. Paths/scopes/rules are constrained, logs and duration have budgets, and one heavy worker is serialized. These measures are not containment against malicious test code or a compromised binary.

Report parsers avoid `pickle` and process bounded JSON records. Report paths/ranges are checked against indexed files; source-identity confidence is retained. Syntax failure rolls back imports. Native trace manifests include source/artifact hashes and stale evidence is not exposed as current. Source and artifact hashes detect mismatch; they are not signatures or trusted attestation of an external report.

Application-level database writes and connection closure are serialized. Use a SQLite runtime with the documented WAL fix; do not rely on this lock to patch SQLite itself. See OPERATIONS.md.

## Residual risks and explicit non-guarantees

Source may contain adversarial syntax, large numbers of facts, secrets, or instructions intended to manipulate an agent. Treat returned source/comments/report messages as **data**, never as authority to change agent policy. Input budgets reduce but do not eliminate resource denial of service. A single parser process is not a safe parser sandbox.

The index stores file/symbol names, code locations, patterns and metadata. Literal contents are hashed by the native collector, but source queries, tool stdout, SARIF properties/codeFlows and external artifacts can still contain secrets. There is no automatic secret scrubber, encryption-at-rest layer or legal data-loss prevention guarantee. Restrict filesystem access and source disclosure to agents using the organization's policy. A cloud subscription client may transmit tool results to its model provider.

Runtime instrumentation does not record ordinary function arguments/locals, but names, file paths, test IDs and third-party logs remain sensitive. Persisted reports are audit data; choose retention accordingly.

Trace hooks can conflict with other profilers, application code can replace them, and subprocess/native effects are not exhaustively observed. Neither a successful test run nor a clean scanner result establishes absence of defects. Dead-code/duplicate/refactoring suggestions need reviewed source evidence and tests before changes.

Large raw reports can consume disk before the importer sees them. Process termination and address-space limits are best effort within the documented platform behavior, not a complete tree-wide CPU/memory/filesystem quota. Windows subprocess-tree termination and macOS/Windows installer behavior were not execution-qualified here.

The custom MCP tools subset was exercised with protocol clients, not an independent official conformance suite or authenticated real clients. No independent code/security reviewer was available. This limitation is visible in VALIDATION.md.

## Before enterprise rollout

Use an approved patched Python/SQLite distribution; freeze/harden the package and any specialist binaries by checksum; exercise native clients under actual enterprise settings; apply OS sandbox/resource restrictions where execution is allowed; run an independent security review; and validate the golden cases/benchmarks in IMPLEMENTATION_PLAN.md. These are release gates, not capabilities implied by the Alpha package metadata.
