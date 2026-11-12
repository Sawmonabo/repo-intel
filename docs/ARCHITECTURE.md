# RepoIntel technical architecture

Research/build snapshot: November 10, 2026, America/New_York. Implementation: 0.1.0. Python-first. This document describes shipped behavior unless explicitly marked as a qualification gap.

## 1. Objective and boundary

Provide coding agents one reusable evidence system for calls, dependencies, runtime behavior, shared-state candidates, history, duplication, special cases, dead-code candidates and test execution. Keep the semantic distinctions that make these facts trustworthy. Do not turn a missing relationship into a claim that a relationship does not exist.

The system owns **one canonical repository index**, not one authoritative index per upstream tool. It has no model provider dependency. Its reasoning consumer is a native Claude Code or Codex client using the user's normal subscription. It does not implement a Claude/Codex harness, model router, OAuth proxy, parallel-agent scheduler, or automated refactoring agent.

The implementation is an executable engineering build. It is not a claim of complete dynamic-Python resolution, Joern/CodeQL semantic parity, a certified vulnerability scanner, or enterprise deployment qualification. Native structural capabilities and MCP behavior were executed in tests. Upstream analyzer contracts were inspected and their normalized schemas fixture-tested, but their binaries could not be downloaded/executed in the build environment. That distinction is exposed through `doctor`/`repo_capabilities`.

## 2. Alternatives and selection

### A. Make Graphy the canonical graph

Rejected after source inspection. Its `CodeGraph` holds a `StableGraph` and multiple in-memory indexes; persistence serializes/deserializes the entire graph blob. `add_edge` deduplicates source/target/kind, so repeated call sites are not distinct edges. This is incompatible with using every source location as first-class evidence and with avoiding a resident whole-repository graph. This is a source-based architectural decision, not an unperformed enterprise performance comparison. [Research S1–S3](SOURCES.md)

### B. Run every proposed analyzer on every refresh

Rejected. Unrelated analyzers do not expose a shared input IR that would let them all consume the same persisted AST, aliases and CFG. Running all of them repeatedly would preserve redundant parsing, indexes, configuration and resource use even behind one MCP name. It also creates contradictory apparent truths: a missing static caller, a runtime call and an import edge are not equivalent facts.

### C. One native canonical extraction; scoped specialist enrichment

Selected. CPython's AST parser supplies version-matched Python syntax. RepoIntel extracts several fact families during one per-file visit, stores them in SQLite, and computes bounded derived relationships on demand. Native Rust-backed specialists are invoked only for an explicit question and scope. Their findings become observations in the same evidence store. They do not become independent persistent graphs or MCP services.

The core is Python plus SQLite's native engine, **not Rust**. A Rust rewrite was not represented as verified when no Rust toolchain was available. The measured benefit comes from bounded scope, disk-backed adjacency and reuse, not from claiming a language alone solves memory complexity. A typed semantic frontend can be added through the existing fact boundary only after it passes the same identity/precision tests; no such integration is implied in this build.

## 3. Components and responsibilities

```text
Claude Code / Codex native subscription clients
                 |
      one MCP tool contract
                 |
  [stdio] OR [small stdio proxies -> authenticated loopback HTTP]
                 |
        Repository application service
          /          |             \
 static collector   query service   one specialist/runtime worker gate
      |                 |           /       |          \
 one-file AST       bounded SQL   pytest +  approved    streamed
 facts/resolver     + traversal   coverage  analyzer    reports
          \             |           \       |          /
                  SQLite WAL
       files + symbols + call sites + typed relations
       observations + runs + test coverage + runtime events
                 |
        private manifests / capped logs / optional raw artifacts
```

`Repository` is the public application boundary. `Store` owns SQL and transactions. `Extractor` never imports target code. `Indexer` owns publication and linking. `QueryService` and `derived` own bounded reads. `Capture` and `Specialists` own trusted execution and post-execution snapshot checks. `Reports` validates normalized observations. `MCPApplication` provides the transport-independent tool contract. `MCPHTTPServer` and `proxy` implement transport and admission limits, not separate analyses.

Most modules are fewer than 250 lines. No database or queue service, daemon supervisor, vector database, browser, LLM SDK or paid service is required.

## 4. Canonical identity and storage

The private state path is derived from the resolved worktree root, or supplied with `--state`. The database records that root and refuses reuse by another worktree. Separate modified worktrees intentionally have separate facts; cross-worktree content-addressed sharing is not implemented.

| Entity | Identity and stored fields | Purpose |
|---|---|---|
| File | Relative POSIX path; SHA-256; size; mtime; module; language; line count; status/error | Source version and coverage inventory. |
| Symbol | Digest of file, qualified lexical scope, kind, definition ordinal; source range; parent; parameter names; decorators; test flag | Disambiguate names and retain structural hierarchy. |
| Call site | File hash, owner ID, line, UTF-8 byte column, kind; expression; argument expressions; resolution hint | Preserve multiple calls between the same functions, including on one line. |
| Call target | Call-site ID + candidate symbol ID | Permit unresolved or multiple targets without fabricating certainty. |
| Reference | File hash, owner, location, name/hint, read/write mode | Support usage queries and candidate suppression. |
| Import | File/owner/line; module/imported name/alias; conditional/type-only flags; resolved target file | Import dependencies and architecture checks. |
| Resource access | Owner/location/resource key/kind/read-write/certainty | Keep lexical globals distinct from possible attributes and literal file/environment identities. |
| Structural pattern | Owner/location/rule/detail | Maintainability candidates, not fixes. |
| Clone signature | Exact and renamed-AST hashes; compressed bounded token sketch; token completeness; candidate bands | Avoid storing a second AST and provide similarity candidates. |
| Literal | Hash, kind, length and source occurrence | Find repeated values without copying possible secrets into an extra value store. |
| Commit membership | Commit hash/timestamp and member paths | Derive co-change without quadratic pair materialization. |
| Run | ID, source snapshot, producer/version, status, timestamps, manifest | Evidence provenance and incomplete/stale status. |
| Finding + evidence | Canonical normalized location/rule key plus distinct run observations | Deduplicate the finding while preserving independent producers. |
| Test execution | Run, pytest context, file, line or source/target line transition | Distinguish execution evidence from behavior assertion. |
| Runtime event | Run/sequence; pid/tid; time; call/return; callee location/name; caller location; test context | Ordered observed runtime evidence without argument values. |

The concrete schema is in `repo_intel/storage.py`. Foreign-key cascades remove stale static facts when a file is replaced/deleted and remove run-associated evidence during explicit retention. Secondary indexes cover caller/target, symbol/file, import target, resource, reference hint, history path, clone signature and runtime/test locations.

The database is one canonical store, but not every byte is globally interned: path strings and provenance necessarily repeat in rows and indexes. Raw runtime/reports may be retained alongside normalized facts until `prune --drop-raw --apply`; that retention is explicit, not claimed to be zero-copy storage. SQLite freed pages are reused rather than automatically shrinking the file.

## 5. Extraction and verification flow

1. **Discover scope.** Prefer streamed `git ls-files -c -o --exclude-standard -z`. Apply configured exclusions and state-directory exclusion. Non-Git fallback uses `os.walk`, configured exclusions and no symlink-directory traversal; it does not reproduce every Git ignore rule.
2. **Read source safely.** Resolve paths within the worktree. Hash bounded bytes, check size/mtime before and after reading, decode Python's declared encoding. File-size, symlink, syntax and decoding failures remain visible inventory rows.
3. **Parse changed Python files once.** Use the host grammar. Collect definitions, scopes, references, calls, import aliases, state syntax, patterns, literal hashes and fingerprints. Release the tree after the file. Text-only inventories for other supported extensions provide mentions, not cross-language semantic graphs.
4. **Resolve from persisted facts.** Build the name index from definitions and reexports, with a bounded 64-pass alias closure. Join call hints to candidate definitions. Relink imports, preferring a concrete submodule when applicable. Report closure incompleteness.
5. **Publish atomically.** Compute the snapshot over extractor identity, configuration and sorted file/hash/status records. Commit all fact changes and metadata in one transaction. WAL readers retain a consistent previous committed snapshot until publication.
6. **Validate evidence at consumption.** Every query carries its snapshot/generation. `repo_source` rehashes the file before returning lines. Observed runs attach only to their recorded snapshot; old-run facts are not returned as current test evidence after a source edit.
7. **Enrich selectively.** A specialist run captures the source manifest, version probe, exact argv, process result and artifact digest. Reindex after execution. Source changes invalidate association to the pre-run snapshot. Normalize and commit the report atomically; reject unsupported schema, escaped paths and impossible primary coordinates.

This verifies provenance, identity and transformation integrity. It **does not establish that an upstream analyzer found every true relationship**. A valid JSON report is not an accuracy certificate.

## 6. Resolution precision

The core is a lexical structural resolver, not a Python type checker or abstract interpreter. Imported names, relative imports, basic reexports, lexical definitions and direct assignment aliases are modeled. Shadowing by parameters prevents naive global name-matching. `self`/`cls` targets are possible receiver candidates, not proof of dynamic method dispatch. Unknown targets remain unresolved call-site records.

Not completely modeled: inheritance/MRO dispatch, descriptors, metaclasses, runtime monkeypatching, framework registration/DI, arbitrary decorators, `getattr`, dynamic imports, plugin discovery, closures/nonlocals in all forms, comprehensions' separate scopes, annotation evaluation policy, arbitrary callable instances, generated code, native extension internals and external consumers. Lambda syntax is recorded with an explicit dynamic-scope finding but has no independent callable identity. One module name may map to several files/source roots; the resolver must not silently choose a definition as uniquely correct in such a collision.

A complete reverse call hierarchy means the transitive closure of **known stored candidates within the request's budget**, not every possible runtime caller. The system intentionally avoids advertising the latter.

## 7. Incremental behavior and failure handling

Unchanged content skips parsing and fact reconstruction. The warm refresh still hashes all discovered files. On a changed/deleted file, its facts are replaced/removed and the persisted binding/call relation is globally relinked. This is content-incremental extraction, **not** fully dependency-local semantic invalidation. Configuration or extractor-version changes force re-extraction.

A malformed changed file does not keep old facts pretending to describe current bytes. Its extraction savepoint rolls back; an error inventory row is published. An interrupted index transaction leaves the prior complete generation, not a half-updated mix. There are no mid-index resumable parser checkpoints: a canceled cold build must start again. Index publication is atomic but cannot create an operating-system snapshot of a worktree being continuously modified; use a stable checkout during high-assurance collection.

No migrations or backward-compatibility shims are included. Unsupported schema versions fail closed; rebuild into a fresh private state directory.

## 8. Derived relations and cross-tool deduplication

Static adjacency, imports, state accesses, runtime events and historical correlation remain different relation types. A test-executed call can corroborate a static candidate at a source location; it is returned through `runtime_calls` rather than replacing all static targets. Unknown runtime source identities are not invented.

Native whole-function clones use exact/renamed AST signatures. Near candidates use bounded five-token shingle comparisons after candidate retrieval; truncation and lack of semantic equivalence are explicit. Imported jscpd block clones live as canonical duplication findings because their unit and similarity metric differ. They are not mislabeled native function clones.

External finding identity includes snapshot, kind, rule and normalized primary/secondary coordinates. Reimporting the same artifact/version/manifest is idempotent. Different observations of the same key produce one finding with multiple bounded provenance records. Different rules or metrics are not automatically equivalent simply because they mention the same line. Cross-rule semantic equivalence would require a separately reviewed rule mapping; none is invented.

The test map uses line ranges and actual test contexts; definition/decorator lines can execute without the function body running. Agents should combine `tests`, `test_arcs` and `runtime_calls` to distinguish those cases. Co-change reports count shared commits and Jaccard overlap, not causal coupling. Shared-state impact is separate from call traversal and does not establish a concrete aliased object's identity.

## 9. Runtime collection and controlled analysis

`capture --trust --python TARGET_PYTHON -- PYTEST_ARGS` runs target tests in their existing environment. Only that environment needs pytest/coverage. A package-owned explicit pytest plugin sets setup/call/teardown contexts. A streaming profiler records Python call/return events and source hashes. coverage.py supplies line and arc evidence, exported as bounded JSONL by the child and normalized by the standard-library host.

The trace and coverage JSONL have explicit byte budgets. Events stop recording after the event/byte cap and report truncation instead of overwriting old events. Profiles exclude values/locals/arguments. Threads without propagated context cannot be honestly attributed to a test. Child processes, xdist workers, native calls and complete async causal relationships are not automatically covered. Existing profiling hooks are not silently replaced.

One interprocess worker lock serializes trusted test capture and specialist execution for a worktree. Static index writes are separately serialized by an application file lock held through connection close, as well as SQLite. Specialist execution has wall timeout, capped output logs, POSIX process-group termination and optional address-space limit. The address-space limit is not a measured-RSS limit or a container-wide memory ceiling. Windows process-tree containment needs operator-level controls.

PyFlow IFDS and PySpector are enrichment engines, not the default index. Their findings/flow paths are retained in native JSON/SARIF provenance. Their internal ASTs/CFGs are not automatically exported into canonical callable edges. The local `flow` operation supplies a selected function's statement CFG and lexical may-reaching definitions, with unsupported constructs explicit. It does not provide whole-program heap/alias/taint completeness.

## 10. Resource budget model

| Resource | Default | What the bound does not guarantee |
|---|---:|---|
| Parser concurrency | 1 | AST object overhead depends on a file's structure. |
| Python file bytes | 8 MiB | Not a hard process RSS limit. |
| Text-only file bytes | 2 MiB | Other languages are not semantically analyzed. |
| SQLite page cache | 8 MiB/connection | OS page cache, row objects and transactions add overhead. |
| Query rows | 200 default, 2,000 maximum | Large individual details can hit the MCP result byte cap. |
| Graph traversal bookkeeping | 10,000 configured nodes | A cutoff means incomplete exploration, not no further impact. |
| SQL execution | 15-second progress deadline | Bounded Python post-processing also has its own limits. |
| HTTP workers | 4, maximum 32 | Each active connection consumes its own cache/results. |
| MCP request/result | 1 MiB / 2 MiB | A larger result is rejected and must be scoped/paged. |
| Runtime events | 1,000,000 | Tests can execute beyond recording coverage. |
| Trace/coverage exported bytes | 256 MiB each | The target process and coverage internal data require their own budget. |
| External report | 1 GiB file; bounded streamed records | Upstream reporter memory is outside the normalizer. |
| Git history | 5,000 commits | Old coupling and renamed lineage may be absent. |

The benchmark script records cold build, unchanged refresh, one-file edit, query distributions, eight readers, peak index-process RSS and state bytes. It does not include analyzer/test subprocess peaks, filesystem cache, arbitrary dynamic frameworks or a semantic comparison against CodeQL. Measured resource behavior is evidence about the generated corpus, not a universal enterprise SLA.

## 11. MCP and subscription boundary

The tools-only MCP implementation supports newline-delimited stdio and stateless Streamable HTTP JSON responses. HTTP is bound to 127.0.0.1 only, validates Host and Origin, requires a local random bearer secret, rejects unsupported versions/content types/oversized requests and limits active request threads. It is not an Internet-facing server or OAuth provider. No SSE stream, remote roots, sampling, model calls or arbitrary SQL tool is advertised. See the protocol and native client sources in [SOURCES](SOURCES.md).

Many agents should share one HTTP service through lightweight stdio proxies. The generated client configuration never overwrites existing agent settings. Source excerpts may still be transmitted by the user's cloud coding client according to that client's account policy; local analysis is not a promise of local inference.

Read tools are the default. Static refresh/history and execution tools are separately operator-enabled. Test/analyzer execution is privileged host code, not sandboxing. High-assurance deployments should start the whole service and its trusted subprocesses in an approved container/worktree with externally enforced CPU/memory/egress controls.

## 12. Remaining production acceptance work

Before treating this as a production enterprise platform, run the supplied acceptance matrix against representative proprietary repositories, execute the exact approved upstream binaries, validate client login/configuration on supported versions, exercise target OS/filesystem behavior, and obtain an independent code/security review. Measure graph precision/recall and false positive/negative behavior on framework-specific fixtures rather than inferring accuracy from a successful benchmark.

Missing high-assurance features are stated, not hidden: complete framework/type dispatch, arbitrary shared-state aliasing and external resource identity, distributed/xdist traces, assertion-strength analysis, a resumable cold-index scheduler, graph delta-local linking, cross-worktree fact sharing, automatic schema migrations, remote multiuser tenancy, independent production audit, and verified CodeQL/Joern-equivalent interprocedural semantics. These are not silently replaced by approximate data under a stronger name.

## SQLite runtime prerequisite

All application writes now acquire `database-writer.lock`, distinct from the heavy-worker lock, and retain it through connection closure and automatic checkpointing. Readers use readonly connections. This reduces concurrent-writer hazards but does not repair the database engine. The official SQLite WAL documentation identifies a WAL-reset fix in 3.51.3 and backports 3.44.6/3.50.7. `doctor` and `status` report version-based safety diagnostics; use a patched build for production and verify any distribution-specific backport. The local test environment used SQLite 3.46.1. WAL state belongs on local, single-host storage, not NFS/SMB. See [S29](SOURCES.md) and [OPERATIONS.md](OPERATIONS.md).
