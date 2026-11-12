from __future__ import annotations

import time
from pathlib import Path
from .config import Settings, default_state, digest, safe_path
from .indexer import Indexer
from .queries import QueryService
from .storage import Store


class Repository:
    def __init__(self,root: str | Path,state: str | Path | None=None):
        self.root=Path(root).resolve()
        if not self.root.is_dir():raise ValueError('Repository root must be an existing directory')
        self.settings=Settings.load(self.root)
        self.store=Store(self.root,Path(state).resolve() if state else default_state(self.root),self.settings)

    def index(self):return Indexer(self.store).run()
    def query(self,kind: str,**kwargs):return QueryService(self.store).run(kind,**kwargs)

    def status(self):
        from .environment import sqlite_safety
        if not self.store.path.exists():return {'indexed':False,'root':str(self.root),'state':str(self.store.state)}
        with self.store.read() as db:
            counts={name:db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                    for name in ('files','symbols','calls','call_targets','imports','accesses','patterns','runs')}
            return {'sqlite':sqlite_safety(),'indexed':True,'root':str(self.root),'state':str(self.store.state),
                'snapshot':Store.get(db,'snapshot'),'generation':Store.get(db,'generation'),
                'indexed_at':Store.get(db,'indexed_at'),'last_index':Store.get(db,'last_index'),
                'parse_errors':db.execute("SELECT count(*) FROM files WHERE status='error'").fetchone()[0],
                'excluded_files':db.execute("SELECT count(*) FROM files WHERE status='excluded'").fetchone()[0],
                'unresolved_calls':db.execute('SELECT count(*) FROM calls c WHERE NOT EXISTS(SELECT 1 FROM call_targets t WHERE t.call=c.id)').fetchone()[0],
                'counts':counts,'semantic_languages':['python'],
                'excluded_patterns':list(self.settings.exclude),
                'memory_policy':{'sqlite_cache_kib':self.settings.sqlite_cache_kib,'parser_workers':1,
                                 'max_file_bytes':self.settings.max_file_bytes},
                'limitations':['No complete dynamic-Python model','No assertion-proof claims','Static queries do not execute source']}

    def source(self,path: str,start: int=1,end: int=80):
        if type(start) is not int or type(end) is not int or start<1 or end<start or end-start>=400:
            raise ValueError('Source window must be 1..400 lines')
        full=safe_path(self.root,path);relative=full.relative_to(self.root).as_posix()
        with self.store.read() as db:
            row=db.execute('SELECT hash,status FROM files WHERE path=?',(relative,)).fetchone()
            if not row or row['status']!='ok':raise ValueError('Source is not successfully indexed')
            if full.stat().st_size>self.settings.max_file_bytes:raise ValueError('Source exceeds file budget')
            data=full.read_bytes()
            if digest(data)!=row['hash']:raise ValueError('Source is stale; refresh the index before reading evidence')
            import io,tokenize
            encoding=tokenize.detect_encoding(io.BytesIO(data).readline)[0] if full.suffix in ('.py','.pyi') else 'utf-8'
            lines=data.decode(encoding).splitlines()
            return {'snapshot':Store.get(db,'snapshot'),'file':relative,'hash':row['hash'],
                    'lines':[{'line':i+1,'text':line} for i,line in enumerate(lines) if start<=i+1<=end],
                    'content_is_untrusted':True}

    def history(self,max_commits=5000):
        from .history import History
        return History(self.store).collect(max_commits)

    def capture(self,args,**kwargs):
        from .capture import Capture
        return Capture(self).run(args,**kwargs)

    def export_manifest(self):
        from .reports import Reports
        return Reports(self).manifest()

    def import_report(self,kind,path,**kwargs):
        from .reports import Reports
        return Reports(self).ingest(kind,Path(path),**kwargs)

    def flow(self,symbol,**kwargs):
        from .flow import Flow
        return Flow(self).run(symbol,**kwargs)

    def run_tool(self,tool,scope,**kwargs):
        from .specialists import Specialists
        return Specialists(self).run(tool,scope,**kwargs)

    def capabilities(self):
        from .specialists import capabilities
        return capabilities()

    def prune(self,**kwargs):
        from .maintenance import Maintenance
        return Maintenance(self).prune(**kwargs)
