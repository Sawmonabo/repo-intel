import json
import subprocess
from pathlib import Path
import pytest
from test_static import engine


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout


def test_history_cochange_is_derived_not_quadratically_stored(tmp_path):
    r,root=engine(tmp_path,{'a.py':'A=1\n','b.py':'B=1\n','with space.py':'X=1\n'})
    git(root,'init','-q');git(root,'config','user.name','Tester');git(root,'config','user.email','tester@local')
    git(root,'add','.');git(root,'commit','-qm','first')
    (root/'a.py').write_text('A=2\n');(root/'b.py').write_text('B=2\n')
    git(root,'add','.');git(root,'commit','-qm','second')
    r.index();out=r.history(max_commits=100)
    assert out['commits']==2
    rows=r.query('cochange',text='a.py')['items']
    assert rows[0]['path']=='b.py' and rows[0]['together']==2
    assert any(x['path']=='with space.py' for x in r.query('history')['items'])


def test_runtime_and_test_map_are_collected_together(tmp_path):
    r,root=engine(tmp_path,{'app.py': 'def inc(x):\n    if x>0:\n        return x+1\n    return 0\n',
        'test_app.py':'from app import inc\ndef test_positive():\n    assert inc(2)==3\ndef test_negative():\n    assert inc(-1)==0\n'})
    r.index()
    with pytest.raises(ValueError,match='trust'):r.capture(['-q'],trust=False)
    out=r.capture(['-q'],trust=True,max_events=10000,timeout=30)
    assert out['exit_code']==0
    events=r.query('runtime',text='inc',limit=500)['items']
    assert any(x['event']=='call' and x['test'].endswith('test_positive|call') for x in events)
    lines=r.query('tests',symbol='app.inc')['items']
    assert any(x['line']==3 and 'test_positive' in x['test'] for x in lines)
    assert any(x['line']==4 and 'test_negative' in x['test'] for x in lines)
    assert out['imported']['arcs']>0
    (root/'app.py').write_text('def inc(x): return x\n');r.index()
    assert not r.query('tests',symbol='app.inc')['items']


def test_trace_limit_is_not_silent(tmp_path):
    r,root=engine(tmp_path,{'test_many.py':'def helper(): return 1\ndef test_many():\n    for _ in range(100): helper()\n'})
    r.index();out=r.capture(['-q'],trust=True,max_events=2,timeout=30)
    assert out['imported']['trace_complete'] is False
    assert out['imported']['events']==2
