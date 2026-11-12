# Operations, budgets and lifecycle

## First deployment

Use local disk, an approved Python interpreter that can parse the target repository's syntax, and a **patched SQLite build**. `repo-intel ... doctor` reports the actual SQLite runtime. SQLite documents a WAL-reset race fixed in 3.51.3 and identified backports 3.44.6/3.50.7; distribution backports need vendor confirmation. The build environment used 3.46.1 and is therefore not itself a certified production database runtime. RepoIntel serializes all application writes through a file lock held until connection close; this is defense in depth, not a substitute for the engine fix. See [S29](SOURCES.md).

State must not be on NFS/SMB or shared across hosts. WAL requires same-host shared memory. Treat the database as a reproducible cache/evidence store, not the only copy of a security finding. Do not open it for writing from arbitrary external scripts while RepoIntel is operating.

Install from the bundled wheel using `install.py`. A new venv is created without network access. Existing environments are not overwritten. Python's `venv`/`ensurepip` must be installed by your operating-system administrator where not included. The package has no mandatory PyPI dependencies. It does not install optional tools or configure accounts.

Run `index`, inspect `status`, and inspect `query files` for parse failures or excluded/oversized inputs. Default Python module roots are `src` and repository root. Configure multiple monorepo source roots explicitly. Colliding module names are not magically resolved by path guessing; evaluate ambiguous symbols before using them in refactors. Other text languages contribute conservative name mentions, not a semantic multi-language graph.

## State and snapshot lifecycle

Default location is the OS user cache under `repo-intel/<hash-of-resolved-root>`. `--state` overrides it. Each state directory is bound to one resolved worktree. Two worktrees need separate state. The package does not rewrite target source, create a branch, or commit application changes.

Each indexing transaction streams discovery, hashes files, extracts changed Python files, deletes obsolete facts, relinks static bindings, then publishes one snapshot atomically. An interrupted transaction rolls back; readers see a coherent previous or next snapshot, not a partially published generation. Failed parses become explicit file status. A failed parse never preserves apparently current old facts from that file.

Warm indexing still reads/hashes discovered source content. A changed file reparses only that file, but the current resolver relinks persisted call/reference facts globally. This is not a fully dependency-local incremental compiler. Long initial writes can create a large WAL; permit disk headroom and keep read transactions brief. The query service opens short-lived readonly transactions.

Runtime and specialist runs retain their source snapshot. Queries exclude obsolete-snapshot runtime/findings by default; `query runs` shows historical identities and status. Historical artifacts are retained until explicitly pruned. An update changes evidence availability, not the original report's historical meaning.

## Default budgets and what they actually bound

| Setting/control | Default | What it does not guarantee |
|---|---:|---|
| Parser workers | 1 | A pathological single AST can still be expensive |
| Python source file bytes | 8 MiB | Not an RSS limit; larger files are skipped explicitly |
| Other text file bytes | 2 MiB | No complete cross-language reference resolution |
| SQLite cache | 8 MiB per connection | Excludes OS cache, SQLite indexes/temp/WAL, Python objects |
| Query rows | 200, hard max 2,000 | Returned relations can still contain supporting metadata |
| Graph traversal | 10,000 nodes | Bounded traversal is not complete blast radius |
| Query time | 15 seconds | A timeout is incomplete, not “no findings” |
| HTTP concurrent workers | 4 | Each active query has its own connection/cache |
| Native trace | 1,000,000 events / 256 MiB | Coverage collection has separate internal memory |
| Capture wall timeout | 3,600 seconds | Does not make repository code safe |
| Specialist wall timeout | 300 seconds | Upstream parsing/reports can be memory-heavy |
| Specialist stdout/stderr budget | 64 MiB combined | Polling permits overshoot; report files use separate limits |
| Import report size | 1 GiB | Larger reports require deliberate rescoping/changes |
| Local selected-function flow | 1,000 nodes / 100,000 facts / 5 seconds | No full interprocedural/heap analysis |

Configuration is strict TOML, unknown keys fail. See `examples/repo-intel.example.toml`. The printed query `limitations` and `truncated` fields are part of the result, not optional footnotes. Never lower a budget and then claim the same completeness.

For a hard process-tree memory cap, launch the service/worker in your approved container or OS resource group. The package's Linux `--address-space-mib` option uses address-space accounting; it is **not** equivalent to RSS or a shared child-process limit. CPU, filesystem, network and subprocess isolation remain external. No arbitrary 1–2 GiB default cap is presented as universally correct.

## One service, many clients

Start `serve http --port 8765 --allow-refresh` on IPv4 loopback. It generates a private bearer-token file, logs the endpoint/token-file location to stderr, and serves a tools-only MCP interface. Run `mcp-config --transport shared` and use the generated native-client stdio-proxy configuration. Each proxy is lightweight; only the shared service performs repository queries. The token is not a model API credential.

Default tools are readonly: status/query/source/flow/capabilities. `--allow-refresh` adds index/history writes. `--allow-execution` adds test and specialist execution, each still requiring explicit trust in the call. Neither option creates a sandbox. Avoid enabling execution when agents review untrusted source.

Direct `serve stdio` is available for a single agent. It uses the same store and does not load a full graph, but each client owns a process. No auto-starting duplicate HTTP daemons or separate specialist MCP services are installed.

The tools-only transport supports protocol versions 2024-11-05, 2025-03-26 and 2025-06-18. It does not implement sampling, prompts, resources, OAuth, persistent sessions, SSE push streams or MCP task continuation. Do not advertise those features to a client. The shared proxy defaults in generated config to a 900-second timeout. Very long initial indexes are better run through the CLI before the agents connect.

A client cancellation/disconnection does not currently cancel an already executing service operation. It remains bounded by its own timeout and worker gate. Do not immediately start duplicate scans after a client timeout; inspect status/manifests first. Busy worker/database-writer locks fail clearly and can be retried after the active operation finishes.

## Retention, backups and recovery

`prune --keep-runs N --drop-raw` previews retained/deleted run IDs and known raw artifacts. Add `--apply` to mutate state. Only managed run artifacts with known filenames are removed; symlinks and repository source are not deletion targets. Logs/manifests are retained. Database run deletion cascades related evidence; orphan finding rows are removed. Deleted SQLite pages become reusable but the physical file does not automatically shrink.

Stop the service before copying the full state directory for backup. Copying only `index.sqlite` while WAL writes are active is unsafe. For a source-only static index, rebuilding is normally simpler than repairing cache corruption. Preserve external run artifacts/manifests you need for audit before rebuilding. The package does not implement online backup, encryption, automatic vacuum or a migration framework; schema mismatch fails closed, consistent with a greenfield release.

## Qualification and troubleshooting

- Missing calls: query unresolved call sites and source; check imports, dynamic dispatch, decorators, source roots and file status. Missing static edges are not proof of dead code.
- Missing runtime data: inspect test exit code, child environment, trace/coverage caps, matching source hashes and subprocess/xdist limitations.
- Missing findings: inspect run status, report version/schema, accepted/rejected counts, source identity and stale snapshot handling.
- High memory: separate indexer, runtime collector and specialist measurements. A stream-normalizing host cannot bound an analyzer's internal graph or coverage context accumulation.
- High disk use: normalized facts and indexes cost space. Raw traces add more. Use targeted runs and explicit retention; do not claim that disk-backed means storage-free.
- HTTP authentication failures: use the generated local token path, correct port and `127.0.0.1` endpoint. Do not weaken origin/host checks to expose the service remotely.

Production acceptance must include the actual enterprise monolith and its framework behaviors. The synthetic benchmark validates a resource profile of the implemented structural workload, not all of these operating conditions.
