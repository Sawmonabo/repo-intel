import json
from pathlib import Path
import pytest


def engine(tmp_path, files):
    root = tmp_path / 'repo'; root.mkdir()
    for name, text in files.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    from repo_intel.service import Repository
    return Repository(root, tmp_path / 'state'), root


def test_exact_calls_and_aliases(tmp_path):
    r, root = engine(tmp_path, {'pkg/__init__.py':'', 'pkg/a.py':
        'def target(x):\n    return x + 1\n', 'pkg/b.py':
        'from .a import target as renamed\ndef caller(x):\n    renamed(x); renamed(x+1)\n    return renamed(x)\n'})
    r.index()
    rows = r.query('calls', symbol='pkg.b.caller')['items']
    assert [(x['line'], x['col']) for x in rows] == [(3,4),(3,16),(4,11)]
    assert all(x['target'] == 'pkg.a.target' for x in rows)
    assert len({x['id'] for x in rows}) == 3
    assert len(r.query('callers', symbol='pkg.a.target')['items']) == 3


def test_shadowing_does_not_resolve_to_import(tmp_path):
    r, _ = engine(tmp_path, {'a.py':'def f(): pass\n', 'b.py':'from a import f\ndef g(f):\n    return f()\n'})
    r.index(); x = r.query('calls', symbol='b.g')['items'][0]
    assert x['target'] is None and x['resolution'] == 'unresolved'


def test_incremental_delete_and_parse_failure(tmp_path):
    r, root = engine(tmp_path, {'a.py':'def f(): pass\n','b.py':'from a import f\ndef g(): f()\n'})
    first = r.index(); second = r.index()
    assert first['parsed_files'] == 2 and second['parsed_files'] == 0
    assert first['snapshot'] == second['snapshot']
    (root/'a.py').unlink(); r.index()
    assert not r.query('symbols', text='a.f')['items']
    assert r.query('calls',symbol='b.g')['items'][0]['target'] is None
    (root/'b.py').write_text('def broken(\n')
    r.index(); assert r.status()['parse_errors'] == 1
    assert not r.query('symbols',text='b.g')['items']


def test_methods_globals_patterns_and_dead_candidates(tmp_path):
    r,_ = engine(tmp_path, {'a.py':'''import os
CACHE = {}
class Service:
    def read(self):
        return self.helper()
    def helper(self):
        return CACHE.get("key")
def update(x):
    global CACHE
    CACHE["key"] = x
    if x == "special":
        try:
            open("config.txt", "w")
        except Exception:
            pass
def _unused():
    return 123
'''} )
    r.index()
    assert r.query('calls',symbol='a.Service.read')['items'][0]['target']=='a.Service.helper'
    state=r.query('state',text='CACHE')['items']
    assert {'read','write'} <= {x['mode'] for x in state}
    assert {'literal_branch','swallowed_exception'} <= {x['rule'] for x in r.query('patterns')['items']}
    assert any(x['qualified_name']=='a._unused' for x in r.query('dead')['items'])


def test_cycles_layers_duplicates_and_mentions(tmp_path):
    r,root=engine(tmp_path, {'a.py':'import b\ndef f(x):\n    y=x+2\n    return y*3\n',
    'b.py':'import a\ndef copy(n):\n    z=n+2\n    return z*3\n',
    'README.md':'f is an external entrypoint\n'})
    r.index()
    assert any(set(x['modules'])=={'a','b'} for x in r.query('cycles')['items'])
    assert r.query('duplicates')['items']
    assert not any(x['qualified_name']=='a.f' for x in r.query('dead')['items'])


def test_read_source_rejects_escape_and_stale(tmp_path):
    r,root=engine(tmp_path, {'a.py':'def f(): return 1\n'});r.index()
    with pytest.raises(ValueError): r.source('../outside',1,5)
    (root/'a.py').write_text('def f(): return 2\n')
    with pytest.raises(ValueError,match='stale'): r.source('a.py',1,5)
