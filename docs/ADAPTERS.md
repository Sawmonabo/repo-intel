# Adapter contracts and reproducible enrichment

All upstream references below resolve through [SOURCES.md](SOURCES.md). The ZIP contains the integration code, **not** external analyzer binaries. No separate analyzer MCP server is started. `doctor` reports installed executables/distributions without running them. Report fixtures establish parsing behavior, not upstream accuracy or release compatibility.

## Execution lifecycle

`run-tool TOOL SCOPE --trust` validates that scope resolves inside the repository, acquires the shared heavy-worker lock, refreshes the index, records the snapshot, probes the tool version, and runs a fixed argument list without a shell. It saves stdout/stderr, the command, duration, exit status and report identity. It refreshes source hashes again before importing. A changed snapshot rejects the enrichment as stale. Normalized evidence is committed atomically; no repository source is modified by RepoIntel.

The external executable itself is trusted code and could modify files or access the network. These controls are not a sandbox. Timeout/log budgets apply to subprocess execution; `--address-space-mib` adds a Linux address-space limit, not a process-tree RSS guarantee. Only one test/analyzer worker runs at a time; busy requests fail explicitly instead of creating a hidden queue.

`--executable /approved/path` chooses a binary where supported. `--python /approved/python` chooses the target interpreter for Tach/test collection. Install specialists into separate approved environments or obtain official release binaries; use absolute executable paths instead of silently adding them to the application dependencies. The source review observed the following **candidate versions**, but did not execute them:

| Tool | Candidate reviewed | Installation reference | Required input |
|---|---|---|---|
| jscpd | 5.4.3 | S04, S06; official release or documented Node launcher | Scoped source path |
| ast-grep | 0.51.1 | S11; official binary/install instructions | Scoped source and explicit rule YAML |
| Tach | 0.35.3 | S07; Python distribution `tach` | Existing `tach.toml` / supported project configuration |
| PyFlow | 0.1.2 | S19; distribution **`pyflow-analysis`** | Scoped Python input |
| PySpector | 0.2.2 | S23; distribution `pyspector`; build prerequisites may apply | Scoped Python input |
| VizTracer | 1.1.1 | S16 | Existing trace JSON; import only |

The current runner records versions but does not enforce a binary allowlist or package hashes. An enterprise release must approve a precise binary/wheel and rerun the integration contract tests against it. Unknown schemas are rejected or counted as rejected records; they are never silently reinterpreted as a different format.

## Exact normalized interfaces

### jscpd

Runner: `jscpd SCOPE --workers 1 --reporters json --output RUN_DIR`, optionally `--similarity NUMBER`. Expected artifact: `jscpd-report.json`.

The imported `duplicates[]` record contains `firstFile.name/start/end` and `secondFile.name/start/end`. `format`, `tokens`, `lines`, `kind`, `similarity`, and `method` are preserved when supplied. Pair ordering is canonicalized, so reversing the sides does not create a second clone finding. Two different ranges stay distinct. The importer does not consume every mode jscpd advertises. Native AST clone groups and block clones remain different representations because their semantics differ. Source: S05.

Three acceptance cases: reversed pair; two clones in the same files at different ranges; one source path outside the root. The normalizer tests exercise these kinds of identity and rejection behavior. Actual clone-detection precision still requires upstream execution on a curated corpus.

### ast-grep

Runner: `ast-grep scan --rule RULE --json=stream --threads 1 SCOPE`. The rule must be an existing repository-relative YAML file. No rewrite flags are passed.

Supported formats: JSON array (`ast-grep`) or one JSON object per line (`ast-grep-jsonl`). Imported fields: `ruleId`, `file`, `range.start/end`, `message`, `severity`. Lines become one-based. Original columns and exclusive-end semantics remain in details. Match text and metavariable source snippets are not copied into canonical findings. Source: S12.

Acceptance cases: multiline match; two rules at one location; malformed/out-of-range source coordinates. The example rule in `examples/demo/rules` is illustrative and not upstream-executed here.

### Tach

`run-tool tach . --python ...` runs `repo_intel.tach_worker` in the chosen interpreter. It invokes the inspected extension API and exports JSONL diagnostics. It does not scrape colored terminal messages. Diagnostics preserve rule/message/severity, available source location and usage/definition module names. The worker refuses to invent configuration when none exists. Source: S09.

`run-tool tach-map .` runs `tach map --direction dependencies --output REPORT`. The map contract is `{file: [dependency_file, ...]}`. Each normalized dependency explicitly records that source-line data is unavailable. It is not inserted as a function-call edge. Source: S08.

Acceptance cases: map without line numbers; configured boundary violation; diagnostic without a source file. Full Tach behavior was not executed in this environment.

### PyFlow / SARIF

Runner uses `pyflow security SCOPE --engine ifds --format sarif --output REPORT`, explicit solver time/memory/fact/queue options, `--ifds-unknown-call-policy preserve`, and `--exit-code-policy report`. Exact executed arguments are retained in the run manifest. Review S20–S21 before using a different version; the flags are an evolving interface.

The general `sarif` importer accepts **SARIF 2.1.0**, explicit `artifactLocation.uri`, region, rule ID, message, level, properties, related locations and codeFlows. Paths are retained as reported evidence, not converted into verified static call edges. Unsupported artifact-index-only locations are rejected. `uriBaseId` is retained but not resolved against arbitrary external base mappings. Full path metadata can contain sensitive source context.

A run reporting no issues does not establish safety. Solver termination, scope incompleteness and unsupported constructs must be evaluated from its manifest/upstream metadata. The selected scope is not automatically expanded to a sound whole-program dependency closure.

Acceptance cases: direct URI result; code-flow path present versus absent; unsupported artifact index. No interprocedural accuracy or RAM guarantee is asserted.

### PySpector

Runner: `pyspector scan SCOPE -f json -o REPORT`. The JSON contract is `summary` plus `issues[]`, containing `rule_id`, `file_path`, `line_number`, `description`, and optional severity/CWE/remediation. Source: S24.

The importer preserves that issue evidence. It does not manufacture parameter propagation, aliases, call chains or full CFGs that are not supplied by the report. Acceptance cases: issue with CWE; multiple rules at one source line; malformed issue/source location. Upstream analyzer execution remains unverified here.

### VizTracer

Import: `import-report viztracer REPORT [--manifest MANIFEST]`. It streams `traceEvents` and metadata. Supported source-bearing phases: `X` complete, `B` begin, `E` end. It parses the documented-style function/file/line name and retains timestamp, duration, process/thread ID and phase. Non-source events are counted separately as rejected/unimported, not invented as Python functions. Overflow metadata marks the run partial. Source: S17.

The trace-array order need not equal chronological call order. `runtime` retains ingestion order and source timestamps. No caller/test association is guessed from adjacency, and cross-thread timestamps are not a causality proof. Acceptance cases: overflow; complete event with duration; no parseable source name.

### Native pytest / coverage

`capture --trust --python TARGET_PYTHON -- PYTEST_ARGS` runs serial pytest in the target interpreter. That environment must contain pytest and coverage. The host package remains standard-library-only.

The plugin switches context for setup, call and teardown; the profile hook streams observed Python call/return events. The child exports CoverageData lines/arcs per context as JSONL using the public API (S15). A manifest records versions, source hashes, artifact hashes, caps, completion flags and test outcome. Only evidence matching the indexed source hashes is imported. Existing coverage/pytest configurations may affect collection; diagnose their interactions rather than assuming universal framework compatibility.

xdist is rejected. Threads started after instrumentation are observed; native/C execution, external processes and complete async causality are not automatically modeled. Profile hooks can conflict with another profiler. Coverage memory during collection is owned by coverage.py and not capped merely because the export is streamed.

## Manual import with provenance

Before an externally managed analyzer run:

```bash
repo-intel --repo /path/to/repo index
repo-intel --repo /path/to/repo manifest > /private/path/source-manifest.json
# Run the approved specialist against that unchanged checkout.
repo-intel --repo /path/to/repo import-report sarif /private/path/report.sarif \
  --manifest /private/path/source-manifest.json --tool-version APPROVED_VERSION
```

A supplied manifest is a **declaration**, not cryptographic proof that the tool actually analyzed the declared files. Without a manifest, the run is `unverified_source_identity`. The tool cannot recover historical source identity from a report that never contained it. Current queries expose producer, run, status and source-identity evidence rather than hiding that distinction.

## Deduplication and failures

Report run identity combines snapshot, format, report digest, manifest and producer version. Reimporting the same evidence is idempotent. Compatible finding identities combine snapshot, category/rule, primary range and related range. Observations from different runs remain attached separately. No fuzzy cross-rule merge asserts semantic equivalence.

The streaming parser has bounded individual records. Syntactically malformed JSON aborts and rolls back the import. A syntactically valid report containing unsupported/invalid individual findings records rejection counts/reasons; valid findings may be retained with partial status. Therefore “complete” describes ingestion of accepted records, **never complete program analysis**. Full report size defaults to at most 1 GiB; source/report/query budgets and raw retention are documented in OPERATIONS.md.
