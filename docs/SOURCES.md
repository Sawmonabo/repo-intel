# Primary-source research register

Reviewed November 10, 2026. Source inspection is not binary validation. Main/master URLs can change; this register records observed facts, not downloaded source hashes. Public release tags and locally executed dependency versions are distinguished in RESEARCH.md.

## S01: Graphy graph implementation

[Graphy graph implementation](https://raw.githubusercontent.com/rosshhun/graphy/main/crates/graphy-core/src/graph.rs)

Source inspection: StableGraph/HashMaps, cloned serialization, endpoint-and-kind edge deduplication.

## S02: Graphy persistence implementation

[Graphy persistence implementation](https://raw.githubusercontent.com/rosshhun/graphy/main/crates/graphy-core/src/storage.rs)

Source inspection: bincode graph stored under a redb key; persistence is not out-of-core graph traversal.

## S03: Graphy manifest

[Graphy manifest](https://raw.githubusercontent.com/rosshhun/graphy/main/Cargo.toml)

Observed main manifest version 1.0.0 and MIT license; not an executed or immutable pinned release.

## S04: jscpd 5.4.3 release

[jscpd 5.4.3 release](https://github.com/kucherenko/jscpd/releases/tag/v5.4.3)

Latest release observed, 2026-11-08, short commit b82d841. Rust detection binary with Node launcher.

## S05: jscpd JSON reporter

[jscpd JSON reporter](https://raw.githubusercontent.com/kucherenko/jscpd/master/rust/crates/cpd-reporter/src/json_reporter.rs)

Source inspection: duplicates, firstFile/secondFile, ranges, clone kind and similarity fields; upstream reporter owns collections.

## S06: jscpd Rust usage

[jscpd Rust usage](https://github.com/kucherenko/jscpd/blob/master/docs/rust.md)

Specialist CLI options and installation reference. Do not assume every advertised mode is imported.

## S07: Tach published distribution

[Tach published distribution](https://pypi.org/project/tach/)

Latest distribution observed 0.35.3, uploaded 2026-10-06; newer than a cached GitHub release listing.

## S08: Tach command reference

[Tach command reference](https://docs.gauge.sh/usage/commands/)

Dependency map JSON and configuration-based checks; map edges do not include call-site coordinates.

## S09: Tach extension interface

[Tach extension interface](https://raw.githubusercontent.com/gauge-sh/tach/main/python/tach/extension.pyi)

parse_project_config/parse_pyproject_config and check signatures; diagnostic properties.

## S10: Tach license

[Tach license](https://raw.githubusercontent.com/gauge-sh/tach/main/LICENSE)

MIT license observed.

## S11: ast-grep release 0.51.1

[ast-grep release 0.51.1](https://github.com/ast-grep/ast-grep/releases/tag/0.51.1)

Latest release observed, 2026-11-02, short commit 5a204b1.

## S12: ast-grep JSON format

[ast-grep JSON format](https://ast-grep.github.io/guide/tools/json.html)

Machine-readable structural matches and zero-based source coordinates.

## S13: ast-grep license

[ast-grep license](https://raw.githubusercontent.com/ast-grep/ast-grep/main/LICENSE)

MIT license observed.

## S14: coverage.py distribution

[coverage.py distribution](https://pypi.org/project/coverage/)

Latest observed 7.17.2, uploaded 2026-11-04; locally executed version was 7.13.3.

## S15: CoverageData public API

[CoverageData public API](https://coverage.readthedocs.io/en/latest/api_coveragedata.html)

Context-aware lines/arcs and supported public data API, rather than binding to private SQLite schema.

## S16: VizTracer distribution

[VizTracer distribution](https://pypi.org/project/viztracer/)

Latest observed 1.1.1; runtime profiler, not a static completeness proof.

## S17: VizTracer report builder

[VizTracer report builder](https://raw.githubusercontent.com/gaogaotiantian/viztracer/master/src/viztracer/report_builder.py)

Source inspection: Chrome trace records and metadata; report construction can materialize trace data.

## S18: PyFlow project

[PyFlow project](https://github.com/ZJU-PL/pyflow)

Research-oriented alpha; Python analysis infrastructure and distinct engines. License file is LICENSE.txt.

## S19: PyFlow distribution

[PyFlow distribution](https://pypi.org/project/pyflow-analysis/)

Latest observed pyflow-analysis 0.1.2, uploaded 2026-10-08. Do not install the unrelated pyflow distribution.

## S20: PyFlow security CLI parser

[PyFlow security CLI parser](https://raw.githubusercontent.com/ZJU-PL/pyflow/main/src/pyflow/cli/security/parser.py)

IFDS, SARIF output, solver budgets, unknown-call policy and exit policy flags.

## S21: PyFlow security command

[PyFlow security command](https://raw.githubusercontent.com/ZJU-PL/pyflow/main/src/pyflow/cli/security/command.py)

Command execution and security-result interface inspected; no independent precision/recall or RSS experiment here.

## S22: PyFlow semantic server

[PyFlow semantic server](https://raw.githubusercontent.com/ZJU-PL/pyflow/main/src/pyflow/cli/lsp.py)

Independent semantic indexing server would add another repository representation; not started by RepoIntel.

## S23: PySpector distribution

[PySpector distribution](https://pypi.org/project/pyspector/)

Latest observed 0.2.2, uploaded 2026-09-28; Rust analysis does not imply all-Rust source parsing.

## S24: PySpector reporter

[PySpector reporter](https://raw.githubusercontent.com/ParzivalHack/PySpector/main/src/pyspector/reporting.py)

JSON summary/issues with rule, file, line, severity and CWE; full solver graph not exported by this contract.

## S25: PySpector license

[PySpector license](https://raw.githubusercontent.com/ParzivalHack/PySpector/main/LICENSE)

Apache-2.0 license observed.

## S26: Pyrefly IDE documentation

[Pyrefly IDE documentation](https://pyrefly.org/en/docs/IDE/)

Alternative semantic/LSP foundation considered; not a drop-in persisted evidence/taint API.

## S27: code2graph project

[code2graph project](https://github.com/NodeDB-Lab/code2graph)

Rust structural extraction candidate, storage-neutral; not executed or embedded in this build.

## S28: CPython AST reference

[CPython AST reference](https://docs.python.org/3/library/ast.html)

Language syntax and UTF-8 byte column conventions. Parsing capabilities follow the executing Python version.

## S29: SQLite WAL documentation

[SQLite WAL documentation](https://www.sqlite.org/wal.html)

Concurrency/local-filesystem constraints and WAL-reset fix: 3.51.3+, or identified 3.44.6/3.50.7 backports.

## S30: MCP transport specification

[MCP transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)

Newline stdio, JSON HTTP responses, origin/authentication and loopback requirements.

## S31: Codex MCP documentation

[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

Official MCP integration; configuration is generated, not written into the user account.

## S32: Codex subscription authentication

[Codex subscription authentication](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)

Native sign-in with ChatGPT and plan usage limits; RepoIntel does not use an inference API.

## S33: Claude Code MCP documentation

[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)

Native local stdio connections and tool permission controls.

## S34: Claude Code authentication

[Claude Code authentication](https://code.claude.com/docs/en/authentication)

Use the official client account/subscription login, not an OAuth inference proxy.

