from __future__ import annotations

import importlib.metadata
import json
import os
import sys
import time
import uuid
from pathlib import Path
from .config import digest,safe_path
from .processes import run_process
from .storage import Store
from .worker_lock import WorkerLock


class Capture:
    def __init__(self,repo):self.repo=repo

    def run(self,args,**kwargs):
        if not kwargs.get('trust',False):
            raise ValueError('Executing tests requires explicit trust=True; this is not a sandbox')
        with WorkerLock(self.repo.store.state):
            return self._run(args,**kwargs)

    def _run(self,args,*,trust=False,python=None,max_events=1000000,max_bytes=256*1024*1024,timeout=3600,address_space_mib=None):
        if not trust:raise ValueError('Executing tests requires explicit trust=True; this is not a sandbox')
        if type(max_events) is not int or max_events<=0:raise ValueError('max_events must be positive')
        if type(max_bytes) is not int or max_bytes<1024:raise ValueError('max_bytes must be at least 1024')
        self.repo.index();snapshot=self.repo.status()['snapshot']
        run=uuid.uuid4().hex;output=self.repo.store.state/'runs'/run
        environment=os.environ.copy()
        package=str(Path(__file__).resolve().parent.parent)
        environment['PYTHONPATH']=package+os.pathsep+environment.get('PYTHONPATH','')
        argv=[python or sys.executable,'-m','repo_intel.capture_runner','--root',str(self.repo.root),
              '--output',str(output),'--snapshot',snapshot,'--events',str(max_events),'--bytes',str(max_bytes),'--',*args]
        result=run_process(argv,self.repo.root,output,timeout=timeout,env=environment,address_space_mib=address_space_mib)
        # Rehash after execution. Mutated source must not inherit an old test proof.
        self.repo.index()
        if not (output/'manifest.json').exists():
            result['imported']={'status':'failed','reason':'collector_did_not_finalize','artifact_directory':str(output)}
            return result
        result['imported']=self.import_run(output,run)
        result['run']=run;result['artifact_directory']=str(output)
        return result

    def import_run(self,output: Path,run: str):
        manifest=json.loads((output/'manifest.json').read_text())
        if manifest.get('schema')!=1 or manifest.get('root')!=str(self.repo.root):raise ValueError('Capture manifest does not match repository')
        events=lines=arcs=0;rejected=0
        with self.repo.store.write() as db:
            snapshot=Store.get(db,'snapshot')
            status='complete' if manifest['trace_complete'] and manifest['coverage_complete'] else 'partial'
            if manifest['snapshot']!=snapshot:status='stale'
            if manifest['exit_code']!=0 and status=='complete':status='tests_failed'
            valid={}
            for path,expected in manifest['file_hashes'].items():
                row=db.execute('SELECT hash FROM files WHERE path=?',(path,)).fetchone()
                valid[path]=bool(row and row['hash']==expected)
                if not valid[path]:rejected+=1
            if rejected and status!='stale':status='partial'
            if db.execute('SELECT 1 FROM runs WHERE id=?',(run,)).fetchone():return {'status':'already_imported','run':run}
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(run,manifest['snapshot'],'runtime',
                'repo-intel-profile+coverage',manifest['coverage_version'],status,manifest['created'],json.dumps(manifest)))
            with (output/'events.jsonl').open(encoding='utf-8') as source:
                for line in source:
                    if len(line)>1024*1024:raise ValueError('Oversized runtime event')
                    event=json.loads(line)
                    if not valid.get(event['file'],False):continue
                    db.execute('INSERT INTO runtime_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (run,event['seq'],event['pid'],event['tid'],event['timestamp_ns'],event['event'],event['file'],
                         event['line'],event['qualname'],event['caller_file'],event['caller_line'],event['test'],'{}'))
                    events+=1
            with (output/'coverage.jsonl').open(encoding='utf-8') as source:
                for encoded in source:
                    if len(encoded)>1024*1024:raise ValueError('Oversized test coverage record')
                    item=json.loads(encoded)
                    if not valid.get(item['file'],False):continue
                    if item['kind']=='line':
                        db.execute('INSERT OR IGNORE INTO test_lines VALUES(?,?,?,?)',
                                   (run,item['test'],item['file'],item['line']));lines+=1
                    elif item['kind']=='arc':
                        db.execute('INSERT OR IGNORE INTO test_arcs VALUES(?,?,?,?,?)',
                                   (run,item['test'],item['file'],item['source'],item['target']));arcs+=1
                    else:raise ValueError('Unknown coverage record kind')
            return {'status':status,'events':events,'lines':lines,'arcs':arcs,
                    'trace_complete':manifest['trace_complete'],'coverage_complete':manifest['coverage_complete'],'rejected_source_files':rejected,'run':run}
