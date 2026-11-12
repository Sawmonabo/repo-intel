"""Exercise an installed wheel outside its checkout, using only stdlib in the host.

Run with the freshly installed Python:
  /path/to/venv/bin/python scripts/smoke_installed.py --test-python /approved/python
The chosen test interpreter must contain pytest and coverage. Target code is only
executed inside a temporary copy of the bundled, trusted demo.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-python',required=True)
    args=parser.parse_args()
    import repo_intel
    checkout=Path(__file__).resolve().parents[1]
    module=Path(repo_intel.__file__).resolve()
    assert not module.is_relative_to(checkout),f'Loaded source checkout instead of wheel: {module}'
    assert importlib.util.find_spec('pytest') is None,'Host smoke environment should have no optional dependencies'
    with tempfile.TemporaryDirectory(prefix='repo-intel-installed-') as name:
        work=Path(name);root=work/'repo';state=work/'state'
        shutil.copytree(checkout/'examples/demo',root)
        env=dict(os.environ);env.pop('PYTHONPATH',None)
        base=[sys.executable,'-m','repo_intel','--repo',str(root),'--state',str(state)]
        def cli(*arguments):
            result=subprocess.run([*base,*arguments],cwd=work,env=env,text=True,capture_output=True,timeout=45)
            assert result.returncode==0,(arguments,result.stderr,result.stdout)
            return json.loads(result.stdout)
        def git(*arguments):
            result=subprocess.run(['git','-c','user.name=Smoke Test','-c','user.email=smoke@example.invalid',*arguments],
                                  cwd=root,env=env,text=True,capture_output=True,timeout=15)
            assert result.returncode==0,result.stderr
        git('init','-q');git('add','.');git('commit','-qm','fixture baseline')
        target=root/'acme/service.py';target.write_text(target.read_text()+'\n# history fixture\n')
        git('add','.');git('commit','-qm','fixture followup')
        cold=cli('index');warm=cli('index');assert warm['parsed_files']==0
        counts={}
        for kind in ('symbols','calls','imports','cycles','architecture','state','coupling','duplicates','literals','patterns','dead','files','references'):
            counts[kind]=len(cli('query',kind)['items'])
        assert counts['cycles'] and counts['patterns'] and counts['calls']
        assert cli('query','callers','--symbol','acme.service.normalize')['items']
        assert cli('query','hierarchy','--symbol','acme.service.normalize')['items']
        assert cli('query','impact','--symbol','acme.service.normalize')['items']
        flow=cli('flow','acme.service.calculate');assert flow
        history=cli('history');assert cli('query','history')['items']
        assert cli('query','cochange','--text','acme/service.py')['items']
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'repo_capture','arguments':{
                      'args':['-q','tests'],'trust':True,'python':args.test_python,'timeout':45}}}]
        process=subprocess.run([*base,'serve','stdio','--allow-execution'],cwd=work,env=env,
            input=''.join(json.dumps(x)+'\n' for x in messages),text=True,capture_output=True,timeout=60)
        assert process.returncode==0,process.stderr
        responses=[json.loads(line) for line in process.stdout.splitlines()]
        assert len(responses)==3,responses
        assert responses[-1]['result']['isError'] is False,responses[-1]
        capture=responses[-1]['result']['structuredContent'];assert capture['exit_code']==0,capture
        for kind in ('tests','test_arcs','runtime','runtime_calls'):
            counts[kind]=len(cli('query',kind)['items']);assert counts[kind]>0,(kind,counts)
        config=cli('mcp-config');assert config['claude']['mcpServers'] and config['codex_toml']
        retention=cli('prune','--keep-runs','1');assert retention['applied'] is False
        output={'installed_module':str(module),'host_optional_dependencies':False,'python':sys.version,
                'cold_index':cold,'warm_index':warm,'query_counts':counts,'history':history,
                'mcp_stdio_responses':len(responses),'capture_exit_code':capture['exit_code'],
                'capture_import':capture['imported'],'config_generated':True,'retention_dry_run':True}
        print(json.dumps(output,indent=2))


if __name__=='__main__':main()
