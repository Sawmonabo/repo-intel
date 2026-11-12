# Data contract and accuracy matrix

## Evidence envelope

`query` / `repo_query` returns `snapshot`, `generation`, `query`, `items`, `truncated`, `next_offset`, `excluded_or_failed_files` and `limitations`. The snapshot identifies the **published index**, not a guarantee that the worktree has not changed since indexing. `repo_source` verifies current bytes before returning an excerpt.

Flat queries are paginated. Hierarchy, cycles, architecture and clone-group results are bounded derived queries and may require a smaller starting scope or a higher configured traversal budget rather than an offset. The API refuses unbounded row requests. Non-integer limits, booleans masquerading as integers and unknown MCP properties are rejected.

Native source lines are one-based. Python AST columns are zero-based UTF-8 **byte offsets**, not LSP UTF-16 character offsets. Native end columns are exclusive. ast-grep's zero-based lines are converted to one-based lines while its coordinate convention is retained in details. SARIF columns retain their one-based convention. A tool that omits a coordinate produces `null`, not a fabricated line 1.

## 1. Call graph

**Primitive records:** symbol ID/qualified name/kind/parent/source range; call-site ID/owner/source line/column/end line/expression; positional and keyword expression strings; resolution hint and separate candidate targets.

**Collection:** one-file AST traversal; lexical binding/import/reexport lookup; SQL join against definitions. Definition-time default/decorator calls belong to the enclosing scope. Repeated calls to the same target remain distinct call sites. Unresolved attribute/callable calls remain visible.

**Queries:** `symbols`, `calls`, `callers`, `references`. `references --symbol` returns known target references, not arbitrary textual mentions. `source` returns hash-validated evidence.

**Verification:** tests cover repeated calls on one line, exact cross-file imports, import shadowing by a parameter, reexport relinking, deletion and syntax failure. There is no measured aggregate call-edge precision/recall over enterprise code. Dynamic dispatch, reflection and framework-specific entry points remain unresolved or possible candidates.

## 2. Hierarchy and blast radius

**Derived records:** reverse/forward bounded breadth-first traversal, depth, reached symbol, `via_symbol`, supporting call file/line/column and resolution category. `impact` adds separately labeled shared-resource dependents. The traversal returns a representative path to each visited symbol, not all exponentially many paths.

**Queries:** `hierarchy` with `direction=incoming|outgoing`; `impact`; `imports`; `coupling`; `tests` to investigate what was executed around affected symbols.

**Verification:** static fixtures exercise cross-module callers and edited/deleted targets. Cyclic graph traversal is bounded by visited sets. The `truncated` flag must be honored. Import/configuration/database-schema/event consumers and unobserved runtime paths can extend the actual blast radius beyond the result. A full enterprise change-impact proof is not delivered by this graph.

## 3. Runtime call flows

**Primitive records:** run/snapshot, sequence, monotonic timestamp, pid/tid, call or return, callee file/code first line/qualified name, parent frame file/current call line, test phase context. No local values or argument values are captured.

**Collection:** selected Python interpreter, explicit pytest plugin, `sys.setprofile` and `threading.setprofile`; bounded JSONL. coverage export happens after test execution in the child interpreter. Existing profiling hooks are not silently replaced.

**Queries:** `runtime` returns collector order; `runtime_calls` groups observed call sites and contexts. Imported VizTracer `X` records contain timestamps/duration; their JSON array order is not promised chronological order, and no caller or test relationship is invented. Sort by timestamp in a downstream visualization only within a compatible clock domain; there is no global causal timeline across native and external runs.

**Verification:** actual temporary pytest runs test positive/negative branches, context attribution, arcs and event-cap reporting; a stopped callback is inert; source changes hide prior-run evidence. Native call counts can include generator/coroutine resumes. C calls, spawned child processes, xdist and distributed traces are not automatic.

## 4. Imports, cycles and layering

**Primitive records:** importing module/file/owner, imported module/name/alias, exact line, relative-import resolution, conditional/type-checking-only flags and target file when uniquely identified.

**Derived records:** iterative Tarjan strongly connected components over a bounded module set; explicit layer/deny-rule violations. Type-checking-only imports do not become runtime-cycle edges. Conditional imports remain possible edges.

**Queries:** `imports`, `cycles`, `architecture`. Native policy is configured in `repo-intel.toml`; it does not guess the intended architecture. Tach can add its richer configuration/interface diagnostics to `findings` through the same worker.

**Verification:** fixtures cover two-module cycles, configured forbidden layering, relative/reexport imports and source changes. The Tach map supplies file dependencies without line numbers; such records keep null lines. Dynamic import strings and plugin loaders require additional review.

## 5. Shared-state reads/writes

**Primitive records:** source owner/location, resource key, resource category, read/write/read-write mode and certainty. Keys include `global:module.NAME`, `attribute:class.field`, `env:KEY` and `file:literal-or-dynamic-expression`.

**Collection:** Python Load/Store/Del contexts; augmented assignment reads; subscript mutations; known mutator method names; literal `open` modes; simple `Path` assignments; environment keys. Calls named `set`, `write`, `update`, etc. are possible effects, not verified API models.

**Queries:** `state`, `coupling`, `impact`. Multiple module consumers of an imported global converge on the imported canonical name where resolved.

**Verification:** fixtures check globals/attribute mutations and imported global identity. A key does not prove concrete object aliasing. Computed file paths, symlink identities, working-directory changes, network cache keys, arbitrary configuration accessors, DB/queue/service names, and interprocess shared state are not comprehensively modeled. Repository-specific ast-grep rules can enrich findings but do not silently create verified read/write edges.

## 6. Git history

**Primitive records:** commit hash/timestamp and member paths. A streamed Git command avoids retaining all history in memory. Path names containing spaces remain intact.

**Derived records:** churn count per file, latest change, shared commit count and Jaccard co-change score. Pairs are calculated for the requested file rather than precomputed for every pair in a large commit.

**Queries:** run `history` first, then `history` or `cochange` queries. The manifest records HEAD and the commit limit. Collection replaces the bounded membership snapshot rather than incrementally adding commits.

**Verification:** a real temporary Git repository has two commits and known file co-change counts. No rename lineage, blame authorship, merge-specific complete parent diff, release tagging or semantic causal coupling is claimed. Large formatting commits and generated files can distort co-change; inspect the evidence before interpreting it architecturally.

## 7. Duplication and repeated values

**Primitive records:** exact/renamed AST fingerprints, compressed token sketch, token count/completeness and candidate bands; literal type/hash/length/location. Literal contents are not separately retained.

**Derived records:** exact renamed-AST groups; scoped near-miss Jaccard candidates from five-token shingles. A whole-function fingerprint is not a general duplicated-block detector. Function names, decorators and return annotations are not part of all equivalence comparisons; this is explicitly a candidate relation, not safe code interchangeability.

**Queries:** `duplicates` for groups; `duplicates --symbol` for near candidates; `literals` for hashes repeated across files; `literal_sites --text HASH` for locations. jscpd block/similarity findings are queried through `findings` with their upstream metric/provenance.

**Verification:** native clone fixtures, compressed-token round trips, source-location checks, jscpd endpoint ordering and idempotent report imports. Token truncation limits retrieval recall; semantically equivalent code with different syntax can be missed. Similarity alone does not authorize consolidation.

## 8. Special cases and needless layers

**Primitive records:** location/rule/detail for `literal_branch`, `mode_flag`, `swallowed_exception`, `sleep_loop`, `retry_loop`, `skipped_test`, `forwarding_wrapper`, `unresolved_star_import` and `dynamic_scope`.

**Collection:** deterministic AST rules from the same per-file parse. Optional ast-grep JSON results carry rule IDs, ranges, severity and message through the unified finding store. The example rule YAML is supplied for inspection, not represented as executed with an unavailable ast-grep binary.

**Queries:** `patterns` with optional rule text. Query callers, state, tests and source around a finding before deciding whether the special case is unnecessary. An abstraction layer cannot be deemed needless merely because a function forwards a call.

**Verification:** native patterns are tested alongside mode flags, swallowed exceptions, loops and skipped tests. General constant propagation, branch satisfiability and equivalence proofs are not supplied.

## 9. Dead-code candidates

**Decision predicate:** non-test function, no decorators, no known incoming call target, no known reading reference, no additional identifier mention in the inventoried repository text, not a configured entry point, and not a protected dunder name.

**Query:** `dead`. The classification is `no_known_usage_candidate`, never `proven_dead`. A use in documentation/string/comment can conservatively suppress a candidate; that favors false-negative avoidance over completeness.

**Verification:** fixtures exercise unreferenced helpers, text mentions, decorated definitions and call/reference updates. Methods invoked through external protocols, reflection, native extensions, public library consumers, generated code and excluded files can still be used. Agents must validate dynamic registrations and contracts. The tool does not automatically delete code.

## 10. Test map

**Primitive records:** pytest node ID and setup/call/teardown context; measured source lines; measured arcs; runtime invocation observations; collector version; test exit code; source hash manifest; completeness flags.

**Queries:** `tests --symbol` returns lines inside the symbol range; `test_arcs --symbol` returns transitions touching the range; `runtime_calls` establishes actual observed invocations. Multiple tests can cover the same line; the context relationship is retained instead of flattening to a single coverage percentage.

**Verification:** real test executions cover two branch outcomes and produce distinct contexts, observed calls and arcs. Source edits invalidate current-snapshot associations. Tests exercising a function do not demonstrate that assertions depend on its behavior. Mutation testing, assertion/data-dependence analysis, full fixture resource tracing and external-service coverage remain additional work.

## Optional local flow contract

`flow` returns a selected function's statement nodes, normal control edges, lexical may-reaching-definition edges, unresolved/external uses, unsupported constructs, fixed-point iterations and any budget stop. It models simple statements, branches and loops. Try/with/match/raise/async and implicit exceptions are not full transfer models. An `analysis_complete` value is scoped to this limited algorithm, not complete Python semantics.

## Verification discipline for agents

For each mapper lane, preserve a small manually reviewed gold set with at least three adversarial cases meaningful to that repository. The shipped tests are reusable regression fixtures, not a substitute for the user's framework-specific gold set. Measure both missed true edges and false positive edges. Store the snapshot and source proof for each decision; rerun after edits. Never convert a successful scan, empty report or passing test count into a stronger statement than its evidence supports.
