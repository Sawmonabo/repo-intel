import json
from pathlib import Path
import pytest
from test_static import engine


def test_atomic_publication_and_root_identity(tmp_path):
    r,root=engine(tmp_path,{'a.py':'def f(): return 1\n'});r.index();snapshot=r.status()['snapshot']
    with pytest.raises(RuntimeError):
        with r.store.write() as db:
            db.execute('DELETE FROM files');raise RuntimeError('cancel')
    assert r.status()['snapshot']==snapshot and r.query('symbols',text='a.f')['items']
    other=tmp_path/'other';other.mkdir()
    from repo_intel.service import Repository
    with pytest.raises(ValueError,match='another'):Repository(other,r.store.state).index()


def test_reexport_incremental_relink(tmp_path):
    r,root=engine(tmp_path,{'pkg/__init__.py':'from .a import f\n','pkg/a.py':'def f(): return 1\n',
        'b.py':'from pkg import f\ndef g(): return f()\n'})
    r.index();assert r.query('calls',symbol='b.g')['items'][0]['target']=='pkg.a.f'
    (root/'pkg/a.py').write_text('def h(): return 1\n')
    r.index();assert r.query('calls',symbol='b.g')['items'][0]['target'] is None


def test_layer_policy_and_query_limits(tmp_path):
    r,root=engine(tmp_path,{'ui.py':'import core\n','core.py':'import ui\n',
        'repo-intel.toml':'layers = [{name="ui", modules=["ui"]}, {name="core", modules=["core"]}]\n'})
    r.index();rows=r.query('architecture')['items'];assert len(rows)==1 and rows[0]['file']=='core.py'
    with pytest.raises(ValueError):r.query('symbols',limit=1000000)
    with pytest.raises(ValueError):r.query('symbols',offset=-1)


def test_file_budget_surfaces_exclusion(tmp_path):
    r,root=engine(tmp_path,{'large.py':'# lots\n'*100,'repo-intel.toml':'max_file_bytes=20\n'})
    r.index();assert r.status()['excluded_files']==1
    assert r.query('files',text='large.py')['items'][0]['error'].startswith('file_budget')


def test_global_cross_module_state_correlation(tmp_path):
    r,_=engine(tmp_path,{'settings.py':'CACHE={}\n','a.py':'from settings import CACHE\ndef put(k,v):\n    CACHE[k]=v\n',
        'b.py':'from settings import CACHE\ndef get(k):\n    return CACHE[k]\n'})
    r.index();rows=r.query('state',text='global:settings.CACHE')['items']
    assert any(x['owner_name']=='a.put' and x['mode']=='write' for x in rows)
    assert any(x['owner_name']=='b.get' and x['mode']=='read' for x in rows)
