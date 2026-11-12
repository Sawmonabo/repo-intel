# RepoIntel implementation and qualification plan

**Goal:** one reusable Python-first local evidence engine with a single MCP interface, ten analysis categories, bounded collection/query work and no model inference APIs.

**Architecture:** one SQLite store per worktree; one-file AST extraction; canonical source/symbol/call-site identities; bounded derived queries; streaming runtime/history/report collectors; scoped specialist enrichment; one shared loopback service with stdio proxies.

**Specification:** [ARCHITECTURE.md](ARCHITECTURE.md) and [DATA_CONTRACT.md](DATA_CONTRACT.md). This document records implemented deliverables separately from the release gates that remain unverified. It is not a claim that an implementation plan alone makes the code enterprise-qualified.

## Constraints and alternatives resolved

Python 3.11+; grammar follows the running interpreter. Core has no third-party Python dependencies. No repository execution during indexing/queries; execution requires operator enablement and explicit trust. No LLM SDK, embeddings, model credentials, provider authentication proxy or telemetry. No silent dynamic-call resolution, safe-deletion assertions or test-proof claims.

Graphy was rejected as canonical after source inspection. Running every proposed tool on every refresh was rejected because it duplicates parsing/state and does not establish common semantics. A new Rust semantic compiler was not invented. The chosen baseline owns cheap canonical facts, while existing specialist outputs add scoped observations. Source locations, uncertainty, snapshot identity and producer status survive the merge.

## Implemented work packages

### 1. Storage, configuration and discovery — implemented and tested

Files: `storage.py`, `config.py`, `discovery.py`, `worker_lock.py`, `environment.py`.

Interfaces: `Settings.load(root)`, `Store(root,state,settings)`, `Store.read()/write()`, content/identity hashes. Storage writes are root-bound, atomic and application-serialized. Reads use query-only transactions. Schema mismatch fails closed. SQLite patch status is exposed, not silently assumed.

Tests: `test_robustness.py` root identity/rollback/budgets; `test_release_hardening.py` writer exclusivity/config/version diagnostics. Acceptance includes deleted/oversized/symlink input, consistent publication and lock release. Configuration never guesses a project policy.

### 2. Static primitive extraction — implemented and tested

Files: `syntax.py`, `extract.py`, `indexer.py`.

Input: bounded source bytes and configured roots. Output: definitions, aliases, call sites, references, imports, read/write candidates, patterns, literal hashes and compact clone signatures. One changed Python file is parsed once; ASTs are released after persistence. Global persisted relinking handles changed name/export relationships.

Tests: `test_static.py` and `test_robustness.py`. Critical cases include imported aliases, shadowing, repeated exact call sites, `self` candidates, cross-module globals, reexports, parse failure and deleted definitions. Unresolved dynamic targets are retained. Module resolution is not a type/heap solver.

### 3. Query and derived relationships — implemented and tested

Files: `queries.py`, `derived.py`, `service.py`.

Interface: `Repository.query(kind, symbol=None, text='', limit=..., offset=..., depth=..., direction=..., run=None)`. Supported kinds are enumerated, not arbitrary SQL. Every result identifies its snapshot and limitations. Traversals and candidate comparisons are bounded. `source()` rechecks content identity.

Tests: exact callers, hierarchy, cycle SCCs, configured layering, shared-state correlation, whole-function clone candidates, repeated values and conservative absence-of-usage candidates. Imported findings retain producer observations and are deduplicated by explicit identity, not message similarity.

### 4. Git and runtime/test evidence — implemented and executed

Files: `history.py`, `runtime_trace.py`, `pytest_plugin.py`, `coverage_export.py`, `capture_runner.py`, `capture.py`, `processes.py`, `limit_exec.py`.

Interfaces: `Repository.history(max_commits)` and `capture(args, trust, python, max_events, max_bytes, timeout, address_space_mib)`. Git stores commit membership, deriving co-change rather than materializing all pairs. Target pytest environment provides coverage. The host imports bounded JSONL with source/artifact verification.

Tests: real temporary Git commits; actual subprocess pytest+coverage; per-test lines/arcs; call sequence; trace caps; stale sources; late thread callbacks; host without coverage installed. Serial pytest only, not xdist/distributed coverage. Captured execution is not assertion proof.

### 5. Specialist contracts — implemented and schema-tested; upstream execution incomplete

Files: `json_stream.py`, `report_formats.py`, `reports.py`, `specialists.py`, `tach_worker.py`.

Interfaces: `Repository.import_report(format,path,manifest,version)` and `run_tool(tool,scope,trust,...)`. Formats cover jscpd, ast-grep array/JSONL, Tach diagnostics/map, PySpector issues, SARIF 2.1.0 and VizTracer events. Runs preserve tool/version/command/scope/status. Invalid records are rejected with counts; malformed documents roll back. Reimports are idempotent. Scoped execution uses one worker and fixed argv without a shell.

Tests: schema variants, reversed clone pairs, repeated observations, source escape, start/end-range bounds, missing flow paths, malformed/oversized JSON, overflow, unknown source identity and a deliberately labeled fixture executable. These tests **do not replace executing approved upstream releases**.

### 6. Demand-driven local flow — implemented and tested

File: `flow.py`.

Interface: `Repository.flow(symbol,max_nodes,max_facts,max_seconds)`. Computes statement-level local CFG and lexical may-reaching definitions for supported constructs, with loop fixed-point/budget reporting. Unsupported exception/async/with/match constructs are explicit. Nested function bodies are not treated as executed by their definition.

Tests: `test_flow.py`. This is not a whole-program CPG, complete control-dependence graph or interprocedural alias/taint solver. Deeper findings can be attached through approved specialists without renaming local flow as semantic parity.

### 7. MCP, CLI and installation — implemented and executed

Files: `mcp.py`, `http_server.py`, `proxy.py`, `client_config.py`, `cli.py`, installers and `pyproject.toml`.

One tools-only interface offers readonly queries, optional refresh/history, and separately enabled execution. Capture accepts the target interpreter and explicit trust. Shared HTTP mode has loopback binding, bearer authentication, Host/Origin checks and bounded concurrency; stdio proxies do not index independently. Config output never edits client settings.

Tests: live JSON-RPC stdio and HTTP, proxy subprocess, malformed input, unauthorized requests, wrong origin/host/version, query limits and missing trust. Offline wheel installation was exercised in a new isolated environment. `scripts/smoke_installed.py` executes outside the source checkout, confirms optional host dependencies are absent, then tests CLI queries/Git and MCP target-environment capture on a temporary demo.

Authenticated Claude Code/Codex sessions and their exact installed versions were not available. Platform testing was Linux only; Windows/macOS instructions are not execution certification.

### 8. Retention, benchmarks and release packaging — implemented; evidence attached

Files: `maintenance.py`, `scripts/benchmark.py`, `scripts/smoke_installed.py`, `evidence/`, docs and wheel.

Pruning previews before applying, preserves source/manifests/logs and only deletes recognized managed artifacts. The benchmark measures cold/warm/edit/query/eight-reader behavior on generated source and records implementation digest, runtime, RSS and disk size. No generated million-line repository or large database is included in the ZIP.

The final regression and installation evidence is in VALIDATION.md. Early failing tests are retained as development evidence, not falsely presented as release failures. No independent reviewer/subagent was available. Local review found and fixed trace-after-close, worker-lock, target-interpreter/trust and report-range issues before packaging.

## Integration with the user's seven-stage agent workflow

**Setup:** lead creates its own isolated branch/worktree/run folder under existing client permissions. Profile language, source roots, tests and protected contracts. Install once, index once and start one shared service. Confirm status, exclusions and unresolved targets. RepoIntel does not silently create branches, decide business contracts or dispatch models.

**Ask:** the lead asks the one-time comments/tests scope question according to the user's workflow; the engine has no LLM or conversation policy.

**Map:** concurrent subscription agents query the same snapshot. Use symbols/calls/imports/state/history/duplicates/patterns/tests with bounded scope. Save findings with snapshot, IDs, locations, inference and limitations. Avoid launching multiple cold indexes.

**Consolidate/redesign:** verify source hashes and observed paths, preserve separate evidence types, reject unsupported conclusions, and route protected-contract changes to human decision. An absent edge is not a deletion proof.

**Baseline:** run approved tests twice where the user's plan requires it. Compare outcome and observed evidence; flaky tests or nondeterministic traces are not silently normalized away. RepoIntel captures one explicitly invoked run at a time and records both runs independently.

**Fix:** the lead's client manages file ownership/dependency waves and commits. Reindex the changed worktree after each wave; do not reuse another worktree's state. Query affected callers/state/tests, then execute the appropriate proof under approved trust.

**Check/final proof:** fresh agents query the new snapshot. Preserve before/after finding identities and source evidence; report partial capabilities and bugs encountered. Retain run manifests, measurements and tests; pruning is explicit. No subscription credentials are copied into a custom service.

## Unmet enterprise-release gates

These are required before calling the package production-qualified, not assertions of work already done.

| Gate | Evidence required | Current status |
|---|---|---|
| Actual monolith scale | Cold/warm/edit/delete/RSS/disk/query p95 on representative 1M–20M LOC repos, large individual modules, high fan-out and long history | Synthetic 1,006,500 LOC only; see measurements |
| Precision/recall | Hand-labeled static call and shared-state truth sets, framework registration/DI/decorators/aliases, unresolved rates | Focused regression fixtures only |
| Specialist execution | Approved exact versions/hashes; real CLI/schema tests and peak memory; source-to-sink positive/negative controls | Source/schema review, not upstream execution |
| Native agent compatibility | Authenticated Claude Code and Codex client sessions, permissions, client timeout and subscription behavior | Protocol-level tests only |
| Operating systems | Supported Linux/macOS/Windows installers, locks, process termination, source paths, encodings and filesystem faults | Linux exercised; other platforms not certified |
| Fault tolerance | Disk full, process kill at publication, concurrent readers/writers, file edits during scan, corrupt database/recovery | Transaction and stale-evidence tests; not full chaos testing |
| Storage runtime | Patched SQLite distribution, local filesystem, backups/retention, long-lived WAL behavior | Diagnostic + app serialization; test SQLite older than fix |
| Independent review | Security/code review and acceptable licenses/supply-chain hashes under enterprise policy | Not performed |

## Golden-case method for each new repository

For every enabled capability, select **at least three nontrivial cases from that actual codebase**, label expected facts manually, and retain a negative control. Examples: a reexported call, a shadowed import and a dynamic callback; a global mutation, alias mutation and computed file path; a real duplicate, intentionally similar nonduplicate and renamed clone; a decorated live function, a plugin string reference and genuinely unused internal function.

Record expected/observed exact locations, false positives, false negatives, unresolved classifications, source snapshot and engine version. Do not accept a mapper merely because it returned three plausible examples. Coverage truth requires observed test contexts and source hashes; behavioral proof additionally requires examining assertions and, where appropriate, mutation/fault-injection tests. Define performance/resource acceptance budgets against the team's actual host, not a vendor's small example.

## Reproduction commands

```bash
python -m pytest -q
python scripts/benchmark.py --workspace /new/empty/benchmark-directory --files 5500
python install.py --prefix /new/isolated/repo-intel-env
/new/isolated/repo-intel-env/bin/python scripts/smoke_installed.py --test-python /approved/test/python
```

The benchmark needs a new workspace so a supposedly cold result cannot reuse an old database. The smoke script executes only its bundled demo copy, not the user's enterprise tests.
