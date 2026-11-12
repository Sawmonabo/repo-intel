from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True)
    p.add_argument('--snapshot',required=True);p.add_argument('--events',type=int,default=1000000)
    p.add_argument('--bytes',type=int,default=256*1024*1024);p.add_argument('args',nargs=argparse.REMAINDER)
    a=p.parse_args();root=Path(a.root).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    import coverage,pytest
    from . import runtime_trace
    os.chdir(root);sys.path.insert(0,str(root))
    if (root/'src').is_dir():sys.path.insert(0,str(root/'src'))
    args=a.args[1:] if a.args[:1]==['--'] else a.args
    if any(x=='-n' or x.startswith('-n') or x.startswith('--numprocesses') for x in args):
        raise ValueError('Capture currently requires serial pytest; xdist needs explicit per-worker instrumentation')
    cov=coverage.Coverage(data_file=str(out/'coverage.db'),branch=True,source=[str(root)],config_file=False)
    runtime_trace.COVERAGE=cov
    trace=runtime_trace.TraceWriter(root,out/'events.jsonl',a.events,a.bytes)
    cov.start();trace.start();code=1
    try:code=int(pytest.main(['-p','repo_intel.pytest_plugin',*args]))
    finally:
        meta=trace.stop();cov.stop();cov.save();runtime_trace.COVERAGE=None
        from .coverage_export import export
        from .reports import file_digest
        meta.update(export(cov.get_data(),root,out/'coverage.jsonl',a.bytes))
        meta['artifact_hashes']={name:file_digest(out/name) for name in ('events.jsonl','coverage.jsonl','coverage.db')}
        meta.update({'schema':1,'snapshot':a.snapshot,'root':str(root),'exit_code':code,
            'created':time.time(),'python':sys.version,'coverage_version':coverage.__version__,
            'pytest_version':pytest.__version__,'collector':'repo-intel-profile+coverage'})
        (out/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return code

if __name__=='__main__':raise SystemExit(main())
