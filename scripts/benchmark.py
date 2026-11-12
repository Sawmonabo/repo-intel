"""Reproducible synthetic benchmark. Not an enterprise acceptance benchmark.

Run from the installed package or checkout:
  python scripts/benchmark.py --workspace /tmp/repo-intel-bench --files 500
The generated source has branches, imports, calls, global accesses and mutations.
"""
from __future__ import annotations
import argparse
import hashlib
import sqlite3
import concurrent.futures
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path


def worker(args):
    from repo_intel.service import Repository
    repo=Repository(Path(args.workspace)/'source',Path(args.workspace)/'state')
    start=time.perf_counter()
    result=repo.index()
    elapsed=time.perf_counter()-start
    try:
        import resource
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss=rss/(1024**2 if sys.platform=='darwin' else 1024)
    except ImportError:rss=None
    result.update(wall_seconds=elapsed,peak_rss_mib=rss)
    print(json.dumps(result))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workspace',required=True,type=Path);p.add_argument('--files',type=int,default=500)
    p.add_argument('--functions',type=int,default=10);p.add_argument('--worker',action='store_true')
    args=p.parse_args()
    if args.worker:return worker(args)
    root=args.workspace/'source';root.mkdir(parents=True,exist_ok=True)
    if (args.workspace/'state').exists():
        raise SystemExit('Use a new benchmark workspace; existing state would invalidate a cold measurement')
    for i in range(args.files):
        imports='from module_0 import anchor\n' if i else 'def anchor(value): return value + 1\n'
        code=imports+f'CONFIG = {{"value": {i}}}\nCACHE = {{}}\n'
        for j in range(args.functions):
            code+=f'''\ndef f_{j}(value, enabled=True):
    total = value + {j}
    initial = CONFIG["value"]
    for step in range(4):
        if enabled:
            total += initial + step
        else:
            total -= step
    CACHE[str(value)] = total
    text = str(total)
    count = len(text)
    if count > 3:
        total += count
    else:
        total -= count
    result = total + value
    return anchor(result)
'''
        (root/f'module_{i}.py').write_text(code)
    line_count=sum(len(f.read_text().splitlines()) for f in root.glob('*.py'))
    def run():
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--workspace',str(args.workspace),'--worker'],
                              text=True,capture_output=True,check=True)
        return json.loads(result.stdout)
    cold=run();warm=run()
    target=root/'module_0.py';target.write_text(target.read_text().replace('total = value + 0','total = value + 99',1))
    edit=run()
    from repo_intel.service import Repository
    repo=Repository(root,args.workspace/'state')
    durations=[]
    for _ in range(100):
        before=time.perf_counter();repo.query('calls',symbol='module_0.f_0');durations.append((time.perf_counter()-before)*1000)
    def query(_):
        before=time.perf_counter();result=repo.query('symbols',text='module_12.');return (time.perf_counter()-before)*1000,result['snapshot']
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        concurrent_results=list(pool.map(query,range(80)))
    files=[f for f in (args.workspace/'state').rglob('*') if f.is_file()]
    source_digest=hashlib.sha256()
    for file in sorted((Path(__file__).resolve().parents[1]/'repo_intel').glob('*.py')):
        source_digest.update(file.name.encode());source_digest.update(file.read_bytes())
    output={'implementation_sha256':source_digest.hexdigest(),'sqlite':sqlite3.sqlite_version,'kind':'synthetic_not_enterprise','python':sys.version,'platform':platform.platform(),'cpu_count':os.cpu_count(),
            'files':args.files,'source_lines':line_count,'cold':cold,'warm':warm,'one_file_edit':edit,
            'query_ms':{'p50':statistics.median(durations),'p95':sorted(durations)[94]},
            'eight_reader_query_ms':{'p50':statistics.median(x[0] for x in concurrent_results),'p95':sorted(x[0] for x in concurrent_results)[75],
                                     'consistent_snapshot':len({x[1] for x in concurrent_results})==1},
            'state_bytes':sum(f.stat().st_size for f in files),'status':repo.status(),
            'limitations':['Repeated generated shapes; not real enterprise dynamic dispatch, frameworks or large individual files',
                           'Peak RSS measured separately in indexing subprocess; excludes filesystem cache and sibling processes',
                           'Warm scan verifies all file content hashes; edit re-links global static call facts']}
    (args.workspace/'result.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
