from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
from pathlib import Path
from .config import Settings

SCHEMA_VERSION = '1'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files(
 path TEXT PRIMARY KEY, module TEXT, hash TEXT NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, status TEXT NOT NULL, error TEXT, seen TEXT NOT NULL,
 language TEXT NOT NULL, lines INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS file_module ON files(module);
CREATE TABLE IF NOT EXISTS symbols(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 qualified_name TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, parent TEXT,
 line INTEGER NOT NULL, col INTEGER NOT NULL, end_line INTEGER NOT NULL, end_col INTEGER,
 params TEXT NOT NULL, decorators TEXT NOT NULL, is_test INTEGER NOT NULL,
 exact_hash TEXT, normalized_hash TEXT, tokens BLOB, token_count INTEGER NOT NULL DEFAULT 0,
 tokens_complete INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS symbol_fqn ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS symbol_name ON symbols(name);
CREATE INDEX IF NOT EXISTS symbol_file ON symbols(file,line,end_line);
CREATE INDEX IF NOT EXISTS symbol_clone ON symbols(normalized_hash);
CREATE TABLE IF NOT EXISTS aliases(
 file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 name TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY(file,name,target));
CREATE TABLE IF NOT EXISTS names(
 name TEXT NOT NULL, symbol TEXT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
 PRIMARY KEY(name,symbol));
CREATE TABLE IF NOT EXISTS calls(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 caller TEXT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
 line INTEGER NOT NULL, col INTEGER NOT NULL, end_line INTEGER NOT NULL,
 expression TEXT NOT NULL, hint TEXT, resolution TEXT NOT NULL,
 arguments TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS calls_caller ON calls(caller,line,col);
CREATE INDEX IF NOT EXISTS calls_hint ON calls(hint);
CREATE TABLE IF NOT EXISTS call_targets(
 call TEXT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
 target TEXT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
 PRIMARY KEY(call,target));
CREATE INDEX IF NOT EXISTS call_target_reverse ON call_targets(target,call);
CREATE TABLE IF NOT EXISTS refs(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 owner TEXT NOT NULL, line INTEGER NOT NULL, col INTEGER NOT NULL,
 name TEXT NOT NULL, hint TEXT, mode TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS refs_hint ON refs(hint);
CREATE INDEX IF NOT EXISTS refs_name ON refs(name);
CREATE TABLE IF NOT EXISTS imports(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 owner TEXT NOT NULL, line INTEGER NOT NULL, module TEXT NOT NULL,
 imported TEXT, alias TEXT, type_only INTEGER NOT NULL, conditional INTEGER NOT NULL,
 target_file TEXT);
CREATE INDEX IF NOT EXISTS imports_file ON imports(file);
CREATE INDEX IF NOT EXISTS imports_target ON imports(target_file);
CREATE TABLE IF NOT EXISTS accesses(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 owner TEXT NOT NULL, line INTEGER NOT NULL, col INTEGER NOT NULL,
 resource TEXT NOT NULL, kind TEXT NOT NULL, mode TEXT NOT NULL, certainty TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS access_resource ON accesses(resource,mode);
CREATE INDEX IF NOT EXISTS access_owner ON accesses(owner);
CREATE TABLE IF NOT EXISTS patterns(
 id TEXT PRIMARY KEY, file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 owner TEXT, line INTEGER NOT NULL, col INTEGER NOT NULL, rule TEXT NOT NULL,
 detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS patterns_rule ON patterns(rule);
CREATE TABLE IF NOT EXISTS mentions(
 file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
 term TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(file,term));
CREATE INDEX IF NOT EXISTS mention_term ON mentions(term);
CREATE TABLE IF NOT EXISTS literals(
 file TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE, owner TEXT,
 line INTEGER NOT NULL, kind TEXT NOT NULL, hash TEXT NOT NULL, length INTEGER,
 PRIMARY KEY(file,line,hash));
CREATE INDEX IF NOT EXISTS literal_hash ON literals(hash);
CREATE TABLE IF NOT EXISTS clone_bands(
 band TEXT NOT NULL, symbol TEXT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
 PRIMARY KEY(band,symbol));
CREATE TABLE IF NOT EXISTS commits(hash TEXT PRIMARY KEY, timestamp INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS commit_files(
 commit_hash TEXT NOT NULL REFERENCES commits(hash) ON DELETE CASCADE,
 path TEXT NOT NULL, PRIMARY KEY(commit_hash,path));
CREATE INDEX IF NOT EXISTS history_path ON commit_files(path,commit_hash);
CREATE TABLE IF NOT EXISTS runs(
 id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, kind TEXT NOT NULL,
 producer TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
 created REAL NOT NULL, manifest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, rule TEXT NOT NULL,
 file TEXT, line INTEGER, end_line INTEGER, related_file TEXT, related_line INTEGER,
 message TEXT NOT NULL, details TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS finding_kind ON findings(kind,file,line);
CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY, finding TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
 run TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS evidence_finding ON evidence(finding);
CREATE TABLE IF NOT EXISTS test_lines(
 run TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, test TEXT NOT NULL,
 file TEXT NOT NULL, line INTEGER NOT NULL, PRIMARY KEY(run,test,file,line));
CREATE INDEX IF NOT EXISTS test_line_file ON test_lines(file,line);
CREATE TABLE IF NOT EXISTS test_arcs(
 run TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, test TEXT NOT NULL,
 file TEXT NOT NULL, source INTEGER NOT NULL, target INTEGER NOT NULL,
 PRIMARY KEY(run,test,file,source,target));
CREATE INDEX IF NOT EXISTS test_arc_file ON test_arcs(file,source,target);
CREATE TABLE IF NOT EXISTS runtime_events(
 run TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, seq INTEGER NOT NULL,
 pid INTEGER, tid INTEGER, timestamp_ns INTEGER NOT NULL, event TEXT NOT NULL,
 file TEXT, line INTEGER, qualname TEXT, caller_file TEXT, caller_line INTEGER,
 test TEXT, details TEXT NOT NULL, PRIMARY KEY(run,seq));
CREATE INDEX IF NOT EXISTS runtime_file ON runtime_events(file,line);
CREATE INDEX IF NOT EXISTS runtime_test ON runtime_events(run,test,seq);
'''


from .worker_lock import WorkerLock


class Store:
    def __init__(self, root: Path, state: Path, settings: Settings):
        self.root, self.state, self.settings = root.resolve(), state.resolve(), settings
        self.path = self.state / 'index.sqlite3'

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            conn = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=10)
        else:
            self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink():
                raise ValueError('State database must not be a symlink')
            conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute(f'PRAGMA cache_size=-{self.settings.sqlite_cache_kib}')
        conn.execute('PRAGMA mmap_size=0')
        conn.execute('PRAGMA temp_store=FILE')
        conn.execute('PRAGMA busy_timeout=10000')
        if readonly:
            conn.execute('PRAGMA query_only=ON')
        else:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def _initialize(self) -> None:
        with contextlib.closing(self._connect()) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
            if exists:
                version = self.get(conn,'schema')
                if version != SCHEMA_VERSION:
                    raise ValueError(f'Unsupported schema {version}; use a fresh state directory')
                if self.get(conn,'root') != str(self.root):
                    raise ValueError('State directory belongs to another repository/worktree')
            else:
                conn.executescript(SCHEMA)
                self.set(conn,'schema',SCHEMA_VERSION)
                self.set(conn,'root',str(self.root))
                conn.commit()
        with contextlib.suppress(OSError):
            self.path.chmod(0o600)

    @staticmethod
    def get(conn: sqlite3.Connection, key: str, default=None):
        row = conn.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def set(conn: sqlite3.Connection, key: str, value) -> None:
        conn.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value)))

    @contextlib.contextmanager
    def write(self):
        # Hold through connection close, including automatic WAL checkpoints.
        # Read-only clients never issue application checkpoints.
        with WorkerLock(self.state,filename='database-writer.lock'):
            self._initialize()
            with contextlib.closing(self._connect()) as conn:
                try:
                    conn.execute('BEGIN IMMEDIATE')
                    yield conn
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    @contextlib.contextmanager
    def read(self):
        if not self.path.exists():
            raise ValueError('Repository is not indexed; run repo-intel index first')
        with contextlib.closing(self._connect(True)) as conn:
            if self.get(conn,'root') != str(self.root):
                raise ValueError('State directory belongs to another repository/worktree')
            if self.get(conn,'schema') != SCHEMA_VERSION:
                raise ValueError('Unsupported schema')
            deadline = time.monotonic() + self.settings.query_timeout_seconds
            conn.set_progress_handler(lambda: int(time.monotonic()>deadline), 10000)
            conn.execute('BEGIN')
            yield conn
            conn.rollback()
