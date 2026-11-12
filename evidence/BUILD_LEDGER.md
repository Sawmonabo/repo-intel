# Build ledger
Plan: docs/IMPLEMENTATION_PLAN.md
Ruling: implement Python-first because the conversation specifies Python monoliths. Non-Python source is inventoried and can receive imported specialist findings, not silently represented as semantically indexed.
Ruling: no compiled Rust toolchain or network package installation is available in the execution container. Use a dependency-free core and validate real local behavior; label external integrations separately.
Ruling: reject Graphy as canonical based on source-inspected resident graph and call-site collapsing.

Implemented: canonical SQLite schema/root identity; strict config; content-hash extraction; lexical call/reference/import/state/pattern facts; compressed clone sketches; bounded derived queries; Git membership; runtime call/coverage export; selected local CFG; report normalizers; specialist worker contracts; one MCP/CLI service; retention; offline installer.
Validation: source/schema-reviewed optional analyzers are not upstream-executed; do not upgrade that evidence level in documentation. No independent reviewer available.
Release fixes: stopped thread callbacks after trace close; unified capture/specialist worker gate; extractor-version invalidation; stdlib-only host coverage ingestion; unique findings with observations; report endpoint bounds; explicit MCP call trust and selectable target interpreter; app DB writer serialization and SQLite patch warning.
Final regression at this stage: 56 passed, evidence/26-final-regression.txt. Installed-wheel smoke executed outside checkout, with no pytest/coverage in host venv and real target-environment test collection: evidence/29-installed-smoke.json.
Qualification gaps are release gates in docs/IMPLEMENTATION_PLAN.md, not silently implied delivered functionality.
