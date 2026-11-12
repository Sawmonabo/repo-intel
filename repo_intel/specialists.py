"""Explicit, serialized specialist execution. No background servers or inference."""
from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

from .config import safe_path
from .processes import run_process
from .worker_lock import WorkerLock

TOOLS=('jscpd','ast-grep','tach','tach-map','pyflow','pyspector')


def capabilities():
    from .environment import sqlite_safety
    distributions={'coverage':'coverage','pytest':'pytest','tach':'tach',
                   'pyflow':'pyflow-analysis','pyspector':'pyspector','viztracer':'viztracer'}
    installed={}
    for name,dist in distributions.items():
        try:installed[name]=importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:installed[name]=None
    return {'sqlite':sqlite_safety(),'core':{'stdlib_only':True,'model_calls':False,'semantic_languages':['python'],
                    'rust_core':False,'storage':'SQLite','framework_models':'not exhaustive'},
            'optional_distributions':installed,
            'optional_executables':{name:shutil.which(name) for name in ('jscpd','ast-grep','tach','pyflow','pyspector','viztracer','git')},
            'adapter_validation':{'jscpd':'source-reviewed; fixture-tested; not upstream-executed in build environment',
                'ast-grep':'source-reviewed; fixture-tested; not upstream-executed in build environment',
                'tach':'source-reviewed extension contract; fixture-tested normalizer; not upstream-executed',
                'pyflow':'source-reviewed CLI and SARIF contract; fixture-tested; not upstream-executed',
                'pyspector':'source-reviewed JSON reporter; fixture-tested; not upstream-executed',
                'viztracer':'source-reviewed trace export; fixture-tested import; not upstream-executed',
                'coverage+pytest':'executed integration tests in build environment'},
            'rejected_default_backends':{'graphy':'Resident graph and endpoint-kind edge deduplication conflict with memory and exact-call-site requirements'}}


class Specialists:
    def __init__(self,repo):
        self.repo=repo

    def run(self,tool: str,scope: str,*,trust=False,executable=None,python=None,rule=None,
            timeout=300,address_space_mib=None,similarity=None):
        if not trust:
            raise ValueError('External analyzer execution requires explicit trust=True; tools are not sandboxed')
        if tool not in TOOLS:
            raise ValueError(f'Unsupported tool; choose {TOOLS}')
        selected=safe_path(self.repo.root,scope)
        if not selected.exists():
            raise ValueError('Analysis scope does not exist')
        executable=executable or ('tach' if tool=='tach-map' else tool)
        resolved=shutil.which(executable) if tool!='tach' else (python or sys.executable)
        if not resolved:
            raise ValueError(f'Analyzer executable not found: {executable}; install the optional tool explicitly')
        if similarity is not None and not 0<float(similarity)<=1:
            raise ValueError('similarity must be in (0,1]')
        with WorkerLock(self.repo.store.state):
            self.repo.index()
            manifest=self.repo.export_manifest()
            output=self.repo.store.state/'runs'/uuid.uuid4().hex
            output.mkdir(parents=True,mode=0o700)
            report=output/'report.json'
            env=os.environ.copy()
            env['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)+os.pathsep+env.get('PYTHONPATH','')
            if tool=='tach':
                version_argv=[resolved,'-c','import importlib.metadata;print(importlib.metadata.version("tach"))']
            else:
                version_argv=[resolved,'--version']
            version_result=run_process(version_argv,self.repo.root,output/'version',timeout=10,log_bytes=65536,env=env)
            version=(output/'version'/'stdout.log').read_text(errors='replace')[:1024].strip() or 'unknown'
            if tool=='jscpd':
                report=output/'jscpd-report.json'
                argv=[resolved,str(selected),'--workers','1','--reporters','json','--output',str(output)]
                if similarity is not None:argv += ['--similarity',str(similarity)]
                kind='jscpd'
            elif tool=='ast-grep':
                if not rule:
                    raise ValueError('ast-grep requires an explicit rule YAML file; no pattern is invented')
                rule_path=safe_path(self.repo.root,rule)
                if not rule_path.is_file():raise ValueError('ast-grep rule file does not exist')
                argv=[resolved,'scan','--rule',str(rule_path),'--json=stream','--threads','1',str(selected)]
                report=output/'stdout.log';kind='ast-grep-jsonl'
            elif tool=='tach':
                argv=[resolved,'-m','repo_intel.tach_worker','--root',str(self.repo.root),'--output',str(report)]
                kind='tach'
            elif tool=='tach-map':
                argv=[resolved,'map','--direction','dependencies','--output',str(report)]
                kind='tach-map'
            elif tool=='pyflow':
                argv=[resolved,'security',str(selected),'--engine','ifds','--format','sarif','--output',str(report),
                      '--ifds-total-max-seconds',str(max(1,min(timeout-5,120))),
                      '--ifds-max-seconds',str(max(1,min(timeout-5,60))),
                      '--ifds-max-memory-bytes',str(512*1024*1024),
                      '--ifds-max-path-edges','200000','--ifds-max-queue-size','100000',
                      '--ifds-unknown-call-policy','preserve','--exit-code-policy','report']
                kind='sarif'
            else:
                argv=[resolved,'scan',str(selected),'-f','json','-o',str(report)]
                kind='pyspector'
            result=run_process(argv,self.repo.root,output,timeout=timeout,env=env,address_space_mib=address_space_mib)
            # Every run records the exact execution contract, including failed runs.
            manifest.update({'tool':tool,'version':version,'argv':argv,
                             'scope':str(selected.relative_to(self.repo.root)),
                             'execution':result,'version_probe':version_result,
                             'upstream_execution_observed':True})
            self.repo.index()
            if self.repo.status()['snapshot']!=manifest['snapshot']:
                result['imported']={'status':'stale','reason':'source_changed_during_analysis'}
            elif result['termination_reason']:
                result['imported']={'status':'failed','reason':result['termination_reason']}
            elif not report.is_file():
                result['imported']={'status':'failed','reason':'expected_report_not_created'}
            else:
                try:
                    result['imported']=self.repo.import_report(kind,report,manifest=manifest,version=version)
                except (ValueError,OSError) as exc:
                    result['imported']={'status':'failed','reason':str(exc)}
            manifest['result']=result
            (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            result['artifact_directory']=str(output)
            result['tool']=tool
            return result
