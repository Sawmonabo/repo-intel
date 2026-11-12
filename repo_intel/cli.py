"""One CLI for collection, evidence queries, analysis, and MCP serving."""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .queries import KINDS
from .report_formats import FORMATS
from .service import Repository
from .specialists import TOOLS


def parser():
    p=argparse.ArgumentParser(prog='repo-intel',description='Local Python code intelligence, without model APIs')
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--repo',type=Path,default=Path.cwd(),help='Repository/worktree root (default: current directory)')
    p.add_argument('--state',type=Path,help='Optional private state directory; default is outside the repository')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('index',help='Atomic, content-hash incremental static indexing')
    sub.add_parser('status',help='Snapshot, indexed capabilities and omissions')
    sub.add_parser('doctor',help='Installed tools and validation status; does not execute external tools')
    query=sub.add_parser('query',help='Read canonical facts and derived relationships')
    query.add_argument('kind',choices=KINDS)
    query.add_argument('--symbol');query.add_argument('--text',default='')
    query.add_argument('--limit',type=int);query.add_argument('--offset',type=int,default=0)
    query.add_argument('--depth',type=int,default=8);query.add_argument('--direction',choices=('incoming','outgoing'),default='incoming')
    query.add_argument('--run')
    source=sub.add_parser('source',help='Read a hash-validated source window')
    source.add_argument('path');source.add_argument('--start',type=int,default=1);source.add_argument('--end',type=int,default=80)
    flow=sub.add_parser('flow',help='Selected-function CFG and lexical reaching definitions')
    flow.add_argument('symbol');flow.add_argument('--max-nodes',type=int,default=1000)
    flow.add_argument('--max-facts',type=int,default=100000);flow.add_argument('--max-seconds',type=float,default=5)
    history=sub.add_parser('history',help='Collect Git commit/file membership, not quadratic co-change pairs')
    history.add_argument('--max-commits',type=int,default=5000)
    capture=sub.add_parser('capture',help='Trusted pytest execution with streaming calls and coverage contexts')
    capture.add_argument('--trust',action='store_true',help='Explicitly allow execution of repository code; NOT a sandbox')
    capture.add_argument('--python',help='Python interpreter of the target test environment')
    capture.add_argument('--max-events',type=int,default=1000000);capture.add_argument('--max-bytes',type=int,default=256*1024*1024)
    capture.add_argument('--timeout',type=float,default=3600);capture.add_argument('--address-space-mib',type=int)
    capture.add_argument('args',nargs=argparse.REMAINDER,help='Arguments after -- are passed to pytest')
    imported=sub.add_parser('import-report',help='Normalize a specialist report; no analyzer is executed')
    imported.add_argument('format',choices=FORMATS);imported.add_argument('path',type=Path)
    imported.add_argument('--manifest',type=Path);imported.add_argument('--tool-version',default='unknown')
    sub.add_parser('manifest',help='Print current source identity for an explicitly captured external run')
    tool=sub.add_parser('run-tool',help='Run a specialist locally, under the one-worker execution gate')
    tool.add_argument('tool',choices=TOOLS);tool.add_argument('scope',help='Repository-relative file/directory scope')
    tool.add_argument('--trust',action='store_true');tool.add_argument('--executable');tool.add_argument('--python')
    tool.add_argument('--rule');tool.add_argument('--timeout',type=float,default=300)
    tool.add_argument('--address-space-mib',type=int);tool.add_argument('--similarity',type=float)
    serve=sub.add_parser('serve',help='Expose the single unified MCP interface')
    serve.add_argument('transport',choices=('stdio','http'))
    serve.add_argument('--port',type=int,default=8765);serve.add_argument('--token-file',type=Path)
    serve.add_argument('--workers',type=int,default=4)
    serve.add_argument('--allow-refresh',action='store_true',help='Allow MCP static refresh/history collection')
    serve.add_argument('--allow-execution',action='store_true',help='Allow MCP agents to execute repository tests and installed analyzers. NOT a sandbox')
    proxy=sub.add_parser('proxy',help='Lightweight stdio bridge to one shared local MCP service')
    proxy.add_argument('--url',required=True);proxy.add_argument('--token-file',required=True)
    proxy.add_argument('--timeout',type=float,default=120)
    config=sub.add_parser('mcp-config',help='Print configuration fragments; never modify agent settings')
    config.add_argument('--transport',choices=('shared','stdio'),default='shared')
    config.add_argument('--port',type=int,default=8765);config.add_argument('--token-file',type=Path)
    prune=sub.add_parser('prune',help='Preview or apply run retention and raw-artifact removal; never modifies repository source')
    prune.add_argument('--keep-runs',type=int,default=10)
    prune.add_argument('--drop-raw',action='store_true')
    prune.add_argument('--apply',action='store_true',help='Without this flag, only report the planned deletion')
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING,stream=sys.stderr)
    try:
        command=args.command
        if command=='proxy':
            from .proxy import run_proxy
            run_proxy(args.url,args.token_file,args.timeout)
            return 0
        repo=Repository(args.repo,args.state)
        if command=='serve':
            from .mcp import MCPApplication,serve_stdio
            app=MCPApplication(repo,allow_refresh=args.allow_refresh,allow_execution=args.allow_execution)
            if args.transport=='stdio':serve_stdio(app)
            else:
                from .http_server import serve_http
                serve_http(app,args.port,args.token_file,args.workers)
            return 0
        if command=='index':result=repo.index()
        elif command=='status':result=repo.status()
        elif command=='doctor':result=repo.capabilities()
        elif command=='manifest':result=repo.export_manifest()
        elif command=='query':result=repo.query(args.kind,symbol=args.symbol,text=args.text,limit=args.limit,
                                               offset=args.offset,depth=args.depth,direction=args.direction,run=args.run)
        elif command=='source':result=repo.source(args.path,args.start,args.end)
        elif command=='flow':result=repo.flow(args.symbol,max_nodes=args.max_nodes,max_facts=args.max_facts,max_seconds=args.max_seconds)
        elif command=='history':result=repo.history(args.max_commits)
        elif command=='capture':
            tests=args.args[1:] if args.args[:1]==['--'] else args.args
            result=repo.capture(tests,trust=args.trust,python=args.python,max_events=args.max_events,
                                max_bytes=args.max_bytes,timeout=args.timeout,address_space_mib=args.address_space_mib)
        elif command=='import-report':
            manifest=json.loads(args.manifest.read_text()) if args.manifest else None
            result=repo.import_report(args.format,args.path,manifest=manifest,version=args.tool_version)
        elif command=='run-tool':result=repo.run_tool(args.tool,args.scope,trust=args.trust,executable=args.executable,
                python=args.python,rule=args.rule,timeout=args.timeout,address_space_mib=args.address_space_mib,similarity=args.similarity)
        elif command=='prune':result=repo.prune(keep_runs=args.keep_runs,drop_raw=args.drop_raw,apply=args.apply)
        elif command=='mcp-config':
            from .client_config import configuration
            result=configuration(repo,args.transport,args.port,args.token_file)
        else:raise ValueError('Unknown command')
        print(json.dumps(result,indent=2,ensure_ascii=True,allow_nan=False))
        if command in ('capture','run-tool') and (result.get('exit_code')!=0 or result.get('imported',{}).get('status') in ('failed','stale')):
            return 1
        return 0
    except (ValueError,OSError,sqlite3.Error,RuntimeError) as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc)}),file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({'error':'cancelled','message':'Operation interrupted; uncommitted database changes roll back'}),file=sys.stderr)
        return 130


if __name__=='__main__':
    raise SystemExit(main())
