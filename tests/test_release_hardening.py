"""Release invariants: wire robustness, retention, provenance, and bounded facts."""
import json
from types import SimpleNamespace

import pytest
from repo_intel.service import Repository
from repo_intel.storage import Store


def make(tmp_path):
    root=tmp_path/'project';root.mkdir()
    (root/'a.py').write_text('VALUE = 1\ndef f(x):\n    return x + VALUE\ndef g():\n    return f(2)\n')
    repo=Repository(root,tmp_path/'state');repo.index()
    return repo


def test_malformed_tool_name_is_protocol_error_not_crash(tmp_path):
    from repo_intel.mcp import MCPApplication
    app=MCPApplication(make(tmp_path))
    for name in ([],{},None,123):
        result=app.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name}})
        assert result['error']['code']==-32602


def test_trace_callback_after_stop_is_inert(tmp_path):
    from repo_intel.runtime_trace import TraceWriter
    repo=make(tmp_path)
    frame=SimpleNamespace(f_code=SimpleNamespace(co_filename=str(repo.root/'a.py'),co_firstlineno=2,
                                                co_qualname='f'),f_back=None)
    trace=TraceWriter(repo.root,tmp_path/'events.jsonl')
    trace.start();trace.stop()
    before=trace.events
    trace.profile(frame,'call',None)
    assert trace.events==before


def test_capture_shares_heavy_worker_gate(tmp_path):
    from repo_intel.worker_lock import WorkerLock
    repo=make(tmp_path)
    with WorkerLock(repo.store.state),pytest.raises(ValueError,match='worker'):
        repo.capture(['-q'],trust=True,timeout=1)


def test_extractor_version_change_invalidates_existing_facts(tmp_path):
    repo=make(tmp_path)
    before=repo.status()['snapshot']
    with repo.store.write() as db:
        Store.set(db,'extractor_version','obsolete')
    changed=repo.index()
    assert changed['parsed_files']==1
    assert repo.status()['snapshot']==before  # Same current engine + same bytes, not a fake content change.
    with repo.store.read() as db:
        assert Store.get(db,'extractor_version')!='obsolete'


def test_clone_tokens_are_compact_and_still_queryable(tmp_path):
    repo=make(tmp_path)
    with repo.store.read() as db:
        row=db.execute("SELECT tokens FROM symbols WHERE qualified_name='a.f'").fetchone()
        assert isinstance(row[0],bytes)
    assert isinstance(repo.query('duplicates',symbol='a.f')['items'],list)


def test_reference_and_branch_arc_queries(tmp_path):
    repo=make(tmp_path)
    refs=repo.query('references',symbol='a.f')['items']
    assert any(r['line']==5 and r['name']=='f' for r in refs)
    with repo.store.write() as db:
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',('fixture',Store.get(db,'snapshot'),'runtime','fixture','1','complete',1,'{}'))
        db.execute('INSERT INTO test_arcs VALUES(?,?,?,?,?)',('fixture','test|call','a.py',2,3))
    arcs=repo.query('test_arcs',symbol='a.f')['items']
    assert arcs[0]['source']==2 and arcs[0]['target']==3


def test_findings_deduplicate_observations_without_losing_provenance(tmp_path):
    repo=make(tmp_path)
    path=tmp_path/'sg.json'
    record={'file':'a.py','ruleId':'candidate','range':{'start':{'line':2,'column':4},'end':{'line':2,'column':10}}}
    path.write_text(json.dumps([record]))
    first=repo.import_report('ast-grep',path,version='one')
    second=repo.import_report('ast-grep',path,version='two')
    rows=repo.query('findings')['items']
    assert len(rows)==1 and len(rows[0]['observations'])==2
    filtered=repo.query('findings',run=first['run'])['items']
    assert len(filtered)==1 and len(filtered[0]['observations'])==1
    assert first['run']!=second['run']


def test_retention_is_dry_run_first_and_does_not_delete_source(tmp_path):
    repo=make(tmp_path)
    with repo.store.write() as db:
        for i in range(3):
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(str(i),Store.get(db,'snapshot'),'report','fixture','1','complete',i,'{}'))
    raw=repo.store.state/'runs'/'abcd';raw.mkdir(parents=True)
    (raw/'events.jsonl').write_text('test artifact')
    (raw/'manifest.json').write_text('{}')
    preview=repo.prune(keep_runs=1,drop_raw=True)
    assert preview['runs_to_remove']==2 and (raw/'events.jsonl').exists()
    result=repo.prune(keep_runs=1,drop_raw=True,apply=True)
    assert result['applied'] is True
    assert len(repo.query('runs')['items'])==1
    assert not (raw/'events.jsonl').exists() and (raw/'manifest.json').exists()
    assert (repo.root/'a.py').exists()


def test_strict_nested_configuration(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    (root/'repo-intel.toml').write_text('layers = [{name="data", modules="not-an-array"}]\n')
    with pytest.raises(ValueError,match='modules'):
        Repository(root)


def test_runtime_host_does_not_require_coverage_library(tmp_path,monkeypatch):
    import sys
    repo=make(tmp_path)
    (repo.root/'test_a.py').write_text('from a import f\ndef test_value():\n    assert f(1)==2\n')
    # Only the selected child test interpreter needs pytest/coverage. The core can remain stdlib-only.
    monkeypatch.setitem(sys.modules,'coverage',None)
    result=repo.capture(['-q'],trust=True,timeout=30)
    assert result['exit_code']==0
    assert result['imported']['lines']>0
    assert repo.query('test_arcs')['items']


def test_database_writer_lock_is_distinct_and_exclusive(tmp_path):
    from repo_intel.worker_lock import WorkerLock
    repo=make(tmp_path)
    with WorkerLock(repo.store.state,filename='database-writer.lock'),pytest.raises(ValueError,match='worker'):
        repo.index()
    assert repo.index()['parsed_files']==0


def test_sqlite_safety_version_reporting():
    from repo_intel.environment import sqlite_safety
    assert sqlite_safety((3,46,1))['known_wal_reset_fix'] is False
    assert sqlite_safety((3,51,3))['known_wal_reset_fix'] is True
    assert sqlite_safety((3,44,6))['known_wal_reset_fix'] is True
    assert sqlite_safety((3,50,7))['known_wal_reset_fix'] is True
    assert sqlite_safety((3,49,9))['known_wal_reset_fix'] is False
