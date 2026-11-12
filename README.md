# RepoIntel 0.1.0

One local CLI and MCP interface for Python repository evidence. No model API, inference service, embeddings, graph server, or model credentials. A standard-library core writes canonical facts to one SQLite database per worktree; optional analyzers enrich the same evidence store.

**Release status:** executable, tested engineering build, not certified for arbitrary enterprise repositories or advertised as a drop-in CodeQL/Joern replacement. The core, real pytest/coverage collection, Git collection, CLI and live MCP transports were exercised. Specialist adapters were reviewed against source and tested with schema fixtures; upstream specialist binaries and authenticated Claude/Codex clients were not available to execute in the build environment. See [validation](docs/VALIDATION.md) before relying on findings.

## Install and index

Requirements: Python 3.11+ with `venv`/`ensurepip`; Git for repository discovery/history. Use a Python version that parses your project's syntax. No Rust toolchain or Node runtime is needed for the core.

From the extracted ZIP, on Linux/macOS/WSL:

```bash
python3 install.py --prefix "$HOME/.local/share/repo-intel-env"
RI="$HOME/.local/share/repo-intel-env/bin/python"
REPO="/absolute/path/to/your/repository"
"$RI" -m repo_intel --repo "$REPO" index
"$RI" -m repo_intel --repo "$REPO" status
"$RI" -m repo_intel --repo "$REPO" query symbols --text YourService --limit 20
```

On Windows PowerShell:

```powershell
python install.py --prefix "$env:LOCALAPPDATA\repo-intel-env"
$RI = "$env:LOCALAPPDATA\repo-intel-env\Scripts\python.exe"
$REPO = "C:\path\to\your\repository"
& $RI -m repo_intel --repo $REPO index
& $RI -m repo_intel --repo $REPO query symbols --limit 20
```

The installer validates the bundled wheel checksum, creates a new isolated environment, and installs it **offline**. It refuses to overwrite an existing environment. It does not edit your shell profile, source repository, Claude settings, Codex settings, or subscriptions. The repository is not executed during indexing. A no-install alternative is `python -m repo_intel ...` from this extracted source directory.

Global options `--repo` and `--state` go **before** the subcommand. State defaults to your user cache, outside the repository. A state directory is bound to a single resolved worktree root.

## One service for all subscription agents

Keep the following service in an operator terminal, using the Python installed above:

```bash
"$RI" -m repo_intel --repo "$REPO" serve http --port 8765 --allow-refresh
```

In another terminal, print client configuration and registration commands:

```bash
"$RI" -m repo_intel --repo "$REPO" mcp-config --transport shared --port 8765
```

Use the printed `registration_commands_posix.claude` and `registration_commands_posix.codex`, or copy the generated Claude JSON / Codex TOML. Both clients connect through a tiny stdio proxy to the **same** authenticated loopback service. The proxy does not parse the repository or hold a graph. The local random bearer secret protects that service; it is **not** a paid model API token.

Sign into the normal Claude Code / Codex clients using your subscription. RepoIntel never logs into, impersonates, proxies authentication to, or invokes a model provider. Subscription limits, enterprise policy, and the client's handling of source code still apply. Source excerpts returned to a cloud coding agent are not guaranteed to remain on your machine merely because analysis is local.

For one client without a shared service, `mcp-config --transport stdio` prints a direct configuration. Each direct client launches a small process, so the shared service is preferred for many agents.

Read queries are enabled by default. `--allow-refresh` permits static reindexing and history collection. **Do not enable `--allow-execution` on untrusted repositories**: it permits tests and installed analyzer subprocesses under your account, not a sandbox. Agent tool confirmation and OS/container restrictions remain your responsibility.

## What is usable now

| Category | Working interface | Interpretation |
|---|---|---|
| Calls and exact call sites | `query calls`, `query callers` | Static lexical/possible targets; unresolved targets remain visible. |
| Hierarchy and impact | `query hierarchy`, `query impact` | Bounded traversal of known calls; shared-state candidates stay separate from call edges. |
| Runtime flows | `capture`, `query runtime`, `query runtime_calls` | Real Python call/return observations, thread/process IDs and test context. |
| Imports and architecture | `query imports`, `query cycles`, `query architecture` | Import SCCs and explicit configured layer/deny policies. |
| Shared state | `query state`, `query coupling` | Globals, imports, attribute/container candidates, environment keys and literal file paths. |
| History | `history`, `query history`, `query cochange` | Bounded Git history; co-change derived at query time. |
| Duplication | `query duplicates`, `query literals`, `query literal_sites` | AST-equivalent/near candidates and hashed literal occurrences; optional jscpd block clones. |
| Special cases | `query patterns` | Syntax-based branches, flags, swallowed errors, sleeps/retries, skips and forwarding wrappers. |
| Dead-code candidates | `query dead`, `query references` | Conservative absence-of-known-usage candidates, never safe-deletion proof. |
| Test map | `query tests`, `query test_arcs` | Observed per-test lines and line transitions, not assertion adequacy. |

Selected-function CFG and lexical reaching definitions are available with `flow QUALIFIED_NAME`. Unsupported constructs and budgets are explicit. This is **not** a complete interprocedural taint/heap analysis. PyFlow/PySpector enrichments are optional and carry their own accuracy/resource limits.

## Useful commands

```bash
"$RI" -m repo_intel --repo "$REPO" query callers --symbol package.module.function
"$RI" -m repo_intel --repo "$REPO" query hierarchy --symbol package.module.function --depth 8
"$RI" -m repo_intel --repo "$REPO" query hierarchy --symbol package.module.function --direction outgoing
"$RI" -m repo_intel --repo "$REPO" query state --text global:
"$RI" -m repo_intel --repo "$REPO" query duplicates --symbol package.module.function
"$RI" -m repo_intel --repo "$REPO" query patterns --text swallowed
"$RI" -m repo_intel --repo "$REPO" flow package.module.function
"$RI" -m repo_intel --repo "$REPO" history --max-commits 5000
"$RI" -m repo_intel --repo "$REPO" query cochange --text src/package/module.py
```

For runtime evidence, your **target test environment** must already contain pytest and coverage.py. The RepoIntel host environment itself needs neither. Do not install dependencies into an enterprise application without its normal approval/lockfile process.

```bash
"$RI" -m repo_intel --repo "$REPO" capture --trust \
  --python "$REPO/.venv/bin/python" --max-events 1000000 --timeout 3600 -- -q tests/unit
"$RI" -m repo_intel --repo "$REPO" query tests --symbol package.module.function
"$RI" -m repo_intel --repo "$REPO" query test_arcs --symbol package.module.function
"$RI" -m repo_intel --repo "$REPO" query runtime_calls --text function
```

Serial pytest is supported. xdist, subprocess coverage, C call tracing, complete async causality and distributed queue/database traces are **not** automatically captured. Trace caps stop recording with explicit truncation; they do not silently overwrite the beginning of a run.

## Optional specialist enrichment

No separate specialist MCP servers are used. Install approved versions of a specialist only when needed, then run it through the unified worker. Nothing is automatically downloaded during indexing.

```bash
"$RI" -m repo_intel --repo "$REPO" doctor
"$RI" -m repo_intel --repo "$REPO" run-tool jscpd src --trust --similarity 0.8
"$RI" -m repo_intel --repo "$REPO" run-tool ast-grep src --trust --rule rules/no-silent-except.yml
"$RI" -m repo_intel --repo "$REPO" run-tool tach . --trust --python "$REPO/.venv/bin/python"
"$RI" -m repo_intel --repo "$REPO" run-tool pyflow src/package --trust --timeout 120
"$RI" -m repo_intel --repo "$REPO" run-tool pyspector src/package --trust
"$RI" -m repo_intel --repo "$REPO" query findings --limit 50
```

The PyFlow distribution is `pyflow-analysis`, not the unrelated `pyflow` package. Existing analyzer reports can be normalized with `import-report`. VizTracer is supported as a report importer, not a second automatic runtime collector. See [adapter contracts](docs/ADAPTERS.md) for installation references, actual fields, supported schemas, and execution-validation gaps.

Each specialist must still parse its selected scope if its API cannot consume our facts. The package prevents redundant **persistent graphs and MCP servers**; it does not falsely promise zero repeated parsing across unrelated upstream engines.

## Retention and resource controls

```bash
# Preview only.
"$RI" -m repo_intel --repo "$REPO" prune --keep-runs 10 --drop-raw
# Explicitly apply. Keeps manifests/logs; never deletes source.
"$RI" -m repo_intel --repo "$REPO" prune --keep-runs 10 --drop-raw --apply
```

The core has one parser worker, an 8 MiB SQLite page cache per connection, bounded source/report/query/trace settings, and no resident whole-repository AST or call graph. These are engineering bounds, **not a universal RSS guarantee** for arbitrary inputs. SQLite index size, temporary files, WAL and coverage collection can still be substantial. Specialist processes need their own measured OS/container budgets.

Configuration example: [repo-intel.example.toml](examples/repo-intel.example.toml). Live HTTP concurrency defaults to four workers. See [operations](docs/OPERATIONS.md) and [security](docs/SECURITY.md).

## Architecture and verification package

- [Architecture, storage, identities and incremental publication](docs/ARCHITECTURE.md)
- [Research and final tool-selection decisions](docs/RESEARCH.md)
- [Ten-capability data contract and accuracy matrix](docs/DATA_CONTRACT.md)
- [Specialist schemas and integration boundaries](docs/ADAPTERS.md)
- [Implementation plan and enterprise acceptance gates](docs/IMPLEMENTATION_PLAN.md)
- [Measured tests and benchmark limitations](docs/VALIDATION.md)
- [Agent operating rules](AGENTS.md)

**Production prerequisite:** use a Python distribution with a patched SQLite runtime. `doctor` reports whether its version includes the documented WAL-reset fix; see [operations](docs/OPERATIONS.md). The build environment itself used an older SQLite and is not a production-runtime certification.

Run the regression suite in an environment with pytest and coverage installed: `python -m pytest -q`. The ZIP includes source, tests, fixtures generated by the tests, benchmark scripts, research provenance, offline installer and a pure-Python wheel. It does not include upstream tool binaries, private repositories, model tokens, or generated enterprise indexes.
