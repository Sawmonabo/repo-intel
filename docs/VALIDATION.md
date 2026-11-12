# Validation and measured results

## Release classification

**RepoIntel 0.1.0 is a runnable, tested engineering release (Alpha), not a fully enterprise-qualified product or a demonstrated CodeQL/Joern replacement.** All ten evidence categories have implemented query/collection paths; several represent candidates or observed executions rather than complete semantic proof. Optional specialist execution and authenticated native-client integration were not fully validated in this environment.

The distinction is deliberate: tests of source identity, report schemas and bounded storage are evidence about those properties, not evidence of complete Python call resolution, no false positives, exhaustive shared-state identity or semantic equivalence.

## Executed verification

| Check | Observed outcome | Artifact |
|---|---|---|
| Full regression suite | **56 tests passed** in the recorded prepackaging run | `evidence/26-final-regression.txt`; final rerun also attached |
| Wheel build | Pure-Python wheel built with setuptools, no runtime dependencies | `evidence/27-release-wheel.txt` |
| Offline installation | New isolated venv; no network package resolution | `evidence/28-release-install.txt` |
| Installed-wheel smoke | Module loaded from site-packages, outside source checkout; host had no pytest dependency | `evidence/29-installed-smoke.json` |
| Demo integration | Static calls/imports/cycles/state/patterns/clones/dead candidates; real two-commit Git history | Same smoke artifact |
| MCP target test capture | Three stdio responses; real pytest execution from selected external test interpreter; exit 0 | Same smoke artifact |
| Runtime/test export | 18 profile events, 10 context-line rows, 15 context-arc rows; complete within demo caps | Same smoke artifact |
| HTTP and proxy | Live local transport, authentication/origin/host/version rejection, real proxy subprocess | `tests/test_mcp.py` in regression suite |
| Million-line resource run | 5,500 generated files, **1,006,500 lines**, eight concurrent readers | `evidence/benchmark-million.json` |

No test failures were suppressed. Earlier `*-red.txt` files intentionally preserve tests failing before the corresponding fix. Those are development evidence, not the final suite result. No independent reviewer, external penetration test, official MCP conformance suite, authenticated Claude session or authenticated Codex session was available.

## Million-line synthetic benchmark

| Measurement | Result |
|---|---:|
| Source files / lines | 5,500 / 1,006,500 |
| Cold index wall time | 127.83 seconds |
| Cold index peak RSS | 107.52 MiB |
| Unchanged refresh | 0.586 seconds |
| One-file edit and relinking | 2.354 seconds |
| Scoped call-query p50 / p95 | 1.12 / 1.46 ms |
| Eight-reader query p50 / p95 | 24.59 / 53.40 ms |
| Concurrent readers used one snapshot | True |
| Normalized state on disk | 767,930,368 bytes (732.36 MiB) |

Environment: `Linux-6.18.57-x86_64-with-glibc2.41`; Python 3.13.5; 5 visible CPUs; SQLite 3.46.1. The full Python build string is in the JSON. The isolated installer used another available base-interpreter build of Python 3.13.5, recorded separately in the smoke artifact.

Implementation digest for all `repo_intel/*.py`, sorted by filename with filename+bytes hashed:

```text
36ac95924c5c074fd2f711575406475263bebcab85a1a775c50992e1f69b75fa
```

Reproduction: `python scripts/benchmark.py --workspace /new/empty/path --files 5500`. The script writes generated Python, runs separate cold/warm/edit processes, records `resource.getrusage` peak RSS, performs 100 scoped call queries and 80 queries with eight readers. It rejects an existing state directory to preserve cold-run meaning. The large generated repo and database are not shipped.

**Interpretation:** this demonstrates a bounded-RAM structural workload for this implementation, not enterprise accuracy or resource guarantees. Repeated generated shapes do not model complex type dispatch, dynamic frameworks, huge individual files, arbitrary aliases or deep taint. The measured query is a small indexed result, not an all-repository blast-radius query. RSS excludes filesystem cache and separate specialist/test processes. Runtime collection and upstream security engines are not included in these index timings. Disk-backed storage trades memory for approximately 732 MiB of indexed facts in this case; it is not zero-storage overhead. No directly comparable CodeQL/Joern run was performed.

## Test coverage by engineering property

`test_static.py` / `test_robustness.py`: source identity, exact call coordinates, aliases and parameter shadowing, reexports, incremental changes/deletion, failed parses, state correlation, SCCs/layers, clone candidates, mention-based dead candidates, size limits and source path/staleness rejection.

`test_runtime_history.py`: actual Git histories and co-change, actual subprocess pytest/coverage collection, test-context evidence, runtime call observations and explicit trace truncation.

`test_reports.py` / `test_specialists.py`: streaming JSON record bounds, fatal-document rollback, schema fixtures, source-range/path validation, producer observations/idempotence, SARIF flow preservation, missing fields, VizTracer overflow, trust requirements, process timeout, lock exclusivity and one labeled executable fixture for the runner contract.

`test_flow.py`: local CFG/reaching definitions, branch merges, loop iteration, call argument references, nested definitions and explicit unsupported constructs/budgets.

`test_mcp.py`: initialization and declared capabilities, stdio errors, bounded/typed arguments, real HTTP requests, auth/origin/host/version controls, shared snapshots, proxy subprocess, actual CLI transport and real target-interpreter capture with required call trust.

`test_release_hardening.py`: late profiler callbacks after stop, shared worker gate, extractor-version invalidation, compressed signatures, reference/test-arc queries, unique findings with observations, retention dryrun, strict config, optional-dependency-free host, database-writer locking and SQLite patch diagnostics.

## What was NOT executed or established

- jscpd, ast-grep, Tach, VizTracer, PyFlow and PySpector upstream binaries. The container could not download/install them. Their adapters are source-reviewed and schema-tested, not proven against the exact candidate release artifacts.
- Precision/recall on the user's proprietary repository, complete static call/alias resolution or a vulnerability-discovery benchmark.
- Native Claude Code/Codex authenticated subscription sessions. Their documented configuration interfaces were used; raw protocol transport tests were executed.
- Windows/macOS runs, Python 3.11/3.12/3.14 CI jobs, xdist, subprocess/distributed tracing, network filesystems, disk-full/chaos testing, production security review or a compiler-quality Rust backend.
- A production-patched SQLite runtime. The tested runtime version predates the documented WAL reset fix. Application writer serialization and a diagnostic are implemented, but production must use an approved patched runtime.

The supplied GitHub Actions workflow is a future CI configuration, not evidence that those remote jobs ran. The code ships without model API credentials or provider SDKs. Normal subscription usage limits and enterprise source-disclosure policy remain the clients' responsibility.

## Qualification decision

Suitable now for controlled local evaluation and read-only code exploration with evidence-aware agents. Trusted demo/test capture and normalized report imports work as documented. Do not automatically delete/refactor code based on candidates or deploy this as an exposed multiuser service. The unmet release gates in IMPLEMENTATION_PLAN.md must be closed before describing it as a production-qualified enterprise tool.
