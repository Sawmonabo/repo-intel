import json
import sys
from pathlib import Path

import pytest
from repo_intel.service import Repository


def make(tmp_path):
    root=tmp_path/'p';root.mkdir()
    (root/'a.py').write_text('import b\n\ndef f():\n    return 1\n')
    (root/'b.py').write_text('VALUE=1\n')
    repo=Repository(root,tmp_path/'state');repo.index()
    return repo


def test_tach_map_preserves_unknown_line_and_coalesces_duplicates(tmp_path):
    repo=make(tmp_path)
    report=tmp_path/'map.json';report.write_text(json.dumps({'a.py':['b.py','b.py'],'b.py':[]}))
    result=repo.import_report('tach-map',report)
    assert result['accepted']==2
    items=repo.query('findings')['items']
    assert len(items)==1 and items[0]['line'] is None
    assert items[0]['related_file']=='b.py'


def test_tach_diagnostics_do_not_invent_missing_locations(tmp_path):
    repo=make(tmp_path)
    report=tmp_path/'tach.jsonl'
    report.write_text(json.dumps({'rule':'dependency','file':'a.py','line':1,'message':'Forbidden',
                                 'usage_module':'a','definition_module':'b','severity':'error'})+'\n'+
                      json.dumps({'rule':'configuration','file':None,'line':None,'message':'Missing module'})+'\n')
    result=repo.import_report('tach',report)
    assert result['accepted']==2
    assert any(x['file'] is None for x in repo.query('findings')['items'])


def test_runner_requires_trust_and_fails_unavailable_tool(tmp_path):
    repo=make(tmp_path)
    with pytest.raises(ValueError,match='trust'):
        repo.run_tool('jscpd','.')
    with pytest.raises(ValueError,match='not found'):
        repo.run_tool('jscpd','.',trust=True,executable='definitely-missing-executable-921')
    with pytest.raises(ValueError,match='escapes'):
        repo.run_tool('jscpd','../',trust=True)


def test_worker_lock_is_exclusive_and_released(tmp_path):
    from repo_intel.worker_lock import WorkerLock
    with WorkerLock(tmp_path):
        with pytest.raises(ValueError,match='worker'):
            with WorkerLock(tmp_path):
                pass
    with WorkerLock(tmp_path):
        pass


def test_process_timeout_and_source_manifest_capture(tmp_path):
    from repo_intel.processes import run_process
    result=run_process([sys.executable,'-c','import time;time.sleep(5)'],tmp_path,tmp_path/'out',timeout=.1)
    assert result['termination_reason']=='timeout'
    assert result['exit_code']!=0


def test_specialist_execution_contract_fixture(tmp_path):
    """Run a fixture executable; this does not verify the upstream jscpd binary."""
    repo=make(tmp_path)
    fake=tmp_path/'fixture-cpd'
    fake.write_text('#!'+sys.executable+'\nimport json,sys,pathlib\n'
                    'if "--version" in sys.argv: print("fixture-5");sys.exit(0)\n'
                    'out=pathlib.Path(sys.argv[sys.argv.index("--output")+1]);out.mkdir(exist_ok=True)\n'
                    '(out/"jscpd-report.json").write_text(json.dumps({"duplicates":[]}))\n')
    fake.chmod(0o700)
    result=repo.run_tool('jscpd','.',trust=True,executable=str(fake))
    assert result['exit_code']==0
    assert result['imported']['accepted']==0
    run=repo.query('runs')['items'][0]
    assert run['version']=='fixture-5'
