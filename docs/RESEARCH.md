# Research, capability audit and selection decisions

Review date: **November 10, 2026**. Primary-source links and a machine-readable register are in [SOURCES.md](SOURCES.md) and `evidence/sources.json`.

## Evidence levels

This delivery distinguishes **documented**, **source-inspected**, **schema-tested**, and **executed**. A CLI advertising “data flow” is not evidence that it exposes a reusable whole-program data-flow graph. A reporter containing a location is not evidence that the finding is correct. A persistent file does not establish out-of-core processing.

The build environment could retrieve documentation through web research but could not download/install upstream packages into its execution container. It had Python, SQLite, Git, pytest and coverage.py. Consequently, the native implementation and those integrations were executed; jscpd, ast-grep, Tach, PyFlow, PySpector and VizTracer were **not** executed. Their source-level contracts were inspected and their normalizers tested against representative schema fixtures. Their runtime performance, recall, framework coverage and release-specific behavior remain qualification work, not verified promises.

## Version and license audit

These are **versions observed in upstream sources**, not a tested dependency lockfile. Mutable source branches inspected for schemas may differ from a published wheel/tag. Specialist execution logs the installed version and arguments; this build does not certify or automatically install those versions.

| Project | Observed upstream version | License observed | Execution in this build |
|---|---|---|---|
| Graphy | main Cargo manifest 1.0.0; immutable latest-release identity not established | MIT | No; rejected as canonical backend |
| jscpd | 5.4.3, release November 8, 2026 | MIT | No; report/runner contract tested |
| Tach | PyPI 0.35.3, October 6, 2026 | MIT | No; extension/map contracts tested |
| ast-grep | 0.51.1, November 2, 2026 | MIT | No; JSON normalizer tested |
| coverage.py | PyPI 7.17.2, November 4, 2026 | Apache-2.0 | **7.13.3** actually executed |
| VizTracer | PyPI 1.1.1 | Apache-2.0 | No; trace import tested |
| PyFlow | `pyflow-analysis` 0.1.2, October 8, 2026 | Apache-2.0 | No; SARIF adapter tested |
| PySpector | PyPI 0.2.2, September 28, 2026 | Apache-2.0 | No; issue-report adapter tested |

References: [S03–S25](SOURCES.md). License observations are not a legal opinion. No upstream analyzer source or binaries are redistributed in the ZIP. The package's own code is MIT-licensed. The installer uses the user's existing Python distribution; its components retain their own licenses.

## Graphy: do not confuse persistence with bounded graph memory

The inspected `CodeGraph` wraps a `petgraph::StableGraph` and several maps. Serialization collects cloned node/edge vectors. Its storage layer serializes that graph using bincode into redb, rather than querying graph neighborhoods directly from independent on-disk rows. The inspected `add_edge` suppresses another edge of the same kind between the same endpoints. [S01, S02](SOURCES.md)

**Design consequence:** this is not a suitable canonical representation for our repeated call-site requirement or memory goal without changing its internals. Two calls from function A to B on different lines must remain two facts. Replacing only its storage file would not remove the resident graph. Therefore Graphy is evaluated but **not installed, embedded, or launched**. Its small published resource example is not used as a capacity guarantee. This corrects the earlier recommendation that treated its persistence as sufficient evidence of scalability.

## jscpd: useful specialist output, not the identity system

The Rust reporter exposes clone pairs with paths, start/end lines, format and token/line counts; optional fields distinguish kind and similarity method. It is suitable for block-level duplication evidence. Its own reporter uses collections and source caching; a streaming importer cannot guarantee the memory use of the process that produced the report. [S04–S06](SOURCES.md)

**Selected role:** explicitly requested scoped clone runs, one worker, structured JSON. Native extraction supplies inexpensive whole-function AST signatures and repeated-literal hashes without invoking another parser during every index. jscpd adds block matching and its richer clone algorithms. Embedding/semantic modes are not automatically enabled. Advertised dead-code or complexity features are not silently treated as implemented normalizer outputs.

**Verification boundary:** locations/schema and deduplication are tested; matching accuracy is not. Similar code is not necessarily behaviorally interchangeable. The exact command/version must be validated against the installed release before production approval.

## Tach: policy semantics are valuable, but the map is not a call graph

Tach enforces declared module dependencies and interfaces. Its dependency map exposes file-to-file adjacency without exact call-site locations. The inspected Python extension exposes project configuration parsing and diagnostic objects. [S07–S10](SOURCES.md)

**Selected role:** optional existing-Tach-policy validation through a small extension worker, with diagnostics imported into the common store. A separate `tach-map` adapter imports coarse dependency observations, clearly marking that source lines are unavailable. The native import collector owns import statements, source coordinates, SCCs and simple configured layer/deny policies. Native policy checks are **not represented as full Tach configuration semantics**.

No second persistent import graph is retained. Tach still needs to scan its chosen project configuration when explicitly run. That repeated work is only justified when its policy rules add information not supplied by the native checker.

## ast-grep: structural pattern specialist

ast-grep reports structured matches, rule IDs, severity and ranges. Its JSON coordinate convention is zero-based; RepoIntel translates line numbers while retaining column/end semantics. [S11–S13](SOURCES.md)

**Selected role:** user-approved project-specific rules, scoped execution, JSONL normalization. Core syntax rules already cover basic equality/sentinel branches, boolean flags, skipped tests, swallowed exceptions, sleep/retry candidates and forwarding wrappers. ast-grep supplies richer structural queries, not general interprocedural resolution or proof that a branch is obsolete. No automatic fix/rewrite command is invoked. The example rule is provided but was not executed by an upstream binary here.

## coverage.py and VizTracer: different evidence, not interchangeable traces

The CoverageData API exposes context-sensitive line and arc execution. It does not establish assertion strength. It is preferable to dependence on coverage.py's private SQLite schema. [S14, S15](SOURCES.md)

**Selected default:** run pytest and coverage inside the project's existing test interpreter; export normalized JSONL there. A native profile hook streams Python call/return records alongside test-phase context. The host tool has no third-party runtime dependency and no need to open the coverage database through private SQL. The actual integration was executed with pytest 9.0.2 and coverage 7.13.3.

VizTracer is a useful richer profiler, but its report builder can materialize data and its buffer behavior requires explicit overflow handling. [S16, S17](SOURCES.md)

**Selected optional role:** import existing VizTracer Chrome trace JSON. Do not run two profilers by default. VizTracer records lacking an immediate caller or test ID retain those unknowns; a name/file/line match does not invent them. Native profiling is not claimed equivalent to VizTracer's multiprocessing/async/native integrations. It supports serial pytest and observed Python frames, not distributed system causality.

## PyFlow and PySpector: optional deeper findings, not free semantic parity

PyFlow identifies itself as an evolving research/alpha framework with multiple IRs and analysis engines. Its security CLI exposes IFDS analysis, SARIF output, unknown-call policy and resource-related options. [S18–S22](SOURCES.md)

**Selected role:** bounded, explicitly scoped security analysis when justified. Preserve SARIF code-flow paths when present; do not infer a graph from a bare issue location. Do not start its MCP/LSP index beside the canonical index. A source scope can exclude relevant callers/dependencies, so scoped results are incomplete unless the selected engine establishes sufficient closure. Report solver budgets and unknown calls instead of treating a clean scan as safety proof.

PySpector's inspected reporter emits issues with rule, CWE, path, line, severity and remediation. That schema does **not** export every call, alias, CFG edge or function summary held internally. Its Python source-to-AST front end and Rust analysis core are different stages. [S23–S25](SOURCES.md)

**Selected role:** optional scoped issue enrichment. A Rust implementation alone neither proves lower memory on the user's monolith nor supplies all data needed for arbitrary graph queries. No numerical accuracy or enterprise memory claim from these projects was reproduced here.

## Alternatives considered

| Alternative | Why considered | Decision |
|---|---|---|
| CPython `ast` | Available, grammar-aware Python syntax, exact positions, no new runtime dependency | Native baseline, one file at a time. Not compiler-quality dynamic dispatch/alias analysis. [S28](SOURCES.md) |
| SQLite | Indexed disk-backed facts, transactions, bounded connection caches | Canonical store, local disk only. Use patched SQLite for production. [S29](SOURCES.md) |
| Pyrefly | Maintained semantic/type intelligence useful for hard call targets | Not silently embedded: LSP semantic state and export/invalidation contracts need separate measured integration. [S26](SOURCES.md) |
| code2graph | Rust structural extraction and storage-neutral graph representation | Candidate future frontend, not an executed dependency in this package. No Rust toolchain was available. [S27](SOURCES.md) |
| More whole-repository graph servers | Convenient ready-made query surfaces | Rejected as the default because they reintroduce independently indexed facts and memory duplication. |
| A new Rust deep-analysis engine | Could control representation/layout | Not represented as delivered: writing a compiler-quality alias/taint engine would not be justified by calling it Rust. |

The delivered core is Python plus SQLite. Its value is a tested evidence contract and bounded architecture, not a claim that Python AST name resolution replaces CodeQL. Measurements in VALIDATION.md apply only to implemented semantics. A faster parser can later implement the same collector contract without changing the query/MCP surface, but no such replacement is included or promised.

## Overlap, missing data and the merge decision

1. **One owner for source identity:** native discovery hashes files; all imported locations must correlate to those files. An analyzer cannot substitute its own notion of the current revision without provenance checks.
2. **One owner for exact static call-site facts:** native extraction preserves source occurrence and target uncertainty. Coarse imports or security locations never become fabricated call edges.
3. **Multiple observations, one finding identity:** compatible category/rule/location pairs deduplicate to one canonical finding with separately retained producer/run observations. Reports whose taxonomies differ are not merged by fuzzy message matching.
4. **Derived instead of materialized:** callers, transitive impact, co-change and duplication queries use stored primitive facts. Do not precompute all file pairs, every call path or every value propagation path.
5. **Keep distinct semantics distinct:** static may-call, observed runtime call, import dependency, lexical state-access candidate and taint path are different relationships. They can support the same investigation without being falsely collapsed.
6. **Gaps are part of the response:** unresolved dynamic calls, excluded files, unmodeled aliases/resources, truncated traces and no-test evidence must remain visible.

The package implements these rules. It does not fully solve heap aliasing, arbitrary framework registration, semantic equivalence of duplicate code, distributed side effects, exhaustive interprocedural data flow, or “all possible breakage.” The complete data contract defines what is available and how to interpret it; it is not a completeness theorem about dynamic Python.

## Subscription compatibility and trust boundary

Official clients support MCP tools and normal subscription sign-in. [S30–S34](SOURCES.md) RepoIntel sends no model requests and stores no provider credentials. The shared service provides data to those native clients, whose normal subscription limits and data policies still apply. The local bearer secret is service access control, not a model API key. No authentication proxy, subscription-token extraction or third-party inference backend is involved.

Protocol-level stdio/HTTP/proxy tests passed locally. Authenticated end-to-end Claude Code/Codex sessions were not available, so those client versions are not claimed tested. Generated configuration uses the documented interfaces; an enterprise rollout should perform the client acceptance check in IMPLEMENTATION_PLAN.md.
