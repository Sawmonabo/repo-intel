from __future__ import annotations

import collections
import hashlib
import io
import json
import re
import subprocess
import time
import tokenize
import uuid
from .config import digest, module_name
from .discovery import discover
from .extract import Extractor
from .storage import Store

EXTRACTOR_VERSION = "0.1.0-facts-2"


class Indexer:
    def __init__(self, store: Store):
        self.store,self.settings=store,store.settings

    def run(self):
        started=time.monotonic();run=uuid.uuid4().hex
        parsed=unchanged=changed=0
        with self.store.write() as db:
            old_config=Store.get(db,'config_hash')
            old_snapshot=Store.get(db,'snapshot')
            force=old_config!=self.settings.digest() or Store.get(db,'extractor_version')!=EXTRACTOR_VERSION
            for relative in discover(self.store.root,self.settings,self.store.state):
                path=self.store.root/relative
                old=db.execute('SELECT hash,status,seen FROM files WHERE path=?',(relative,)).fetchone()
                if old and old['seen']==run:continue
                language='python' if path.suffix in ('.py','.pyi') else path.suffix.lstrip('.')
                module=module_name(relative,self.settings) if language=='python' else None
                status,error,text='ok',None,''
                try:
                    stat=path.lstat()
                    budget=self.settings.max_file_bytes if language=='python' else self.settings.max_text_bytes
                    if path.is_symlink():
                        status,error='excluded','symlink_not_followed';content=b''
                    elif stat.st_size>budget:
                        status,error='excluded',f'file_budget:{stat.st_size}>{budget}';content=b''
                    else:
                        content=path.read_bytes()
                        after=path.stat()
                        if (stat.st_mtime_ns,stat.st_size)!=(after.st_mtime_ns,after.st_size):
                            raise ValueError('File changed while being read; retry indexing')
                    file_hash=digest(content) if status=='ok' else digest(f'{status}:{stat.st_size}:{stat.st_mtime_ns}')
                    if old and old['hash']==file_hash and not force:
                        db.execute('UPDATE files SET seen=?,mtime_ns=? WHERE path=?',(run,stat.st_mtime_ns,relative))
                        unchanged+=1;continue
                    if status=='ok':
                        encoding=tokenize.detect_encoding(io.BytesIO(content).readline)[0] if language=='python' else 'utf-8'
                        text=content.decode(encoding)
                except FileNotFoundError:
                    continue
                except (UnicodeError,SyntaxError,ValueError,OSError) as exc:
                    status,error='error',f'{type(exc).__name__}: {exc}'[:500]
                    stat=path.lstat();file_hash=digest(f'error:{stat.st_size}:{stat.st_mtime_ns}');text=''
                db.execute('DELETE FROM files WHERE path=?',(relative,))
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (relative,module,file_hash,stat.st_size,stat.st_mtime_ns,status,error,run,language,len(text.splitlines())))
                changed+=1
                if status!='ok':continue
                # Count text mentions for conservative candidate suppression. One file at a time.
                terms=collections.Counter(re.findall(r'\b[A-Za-z_]\w*\b',text))
                db.executemany('INSERT INTO mentions VALUES(?,?,?)',((relative,k,v) for k,v in terms.items()))
                del terms
                if language=='python':
                    db.execute('SAVEPOINT parse_file')
                    try:
                        Extractor(db,relative,module,file_hash,self.settings).collect(text)
                        parsed+=1
                    except (SyntaxError,RecursionError,ValueError) as exc:
                        db.execute('ROLLBACK TO parse_file')
                        db.execute("UPDATE files SET status='error',error=? WHERE path=?",(f'{type(exc).__name__}: {exc}'[:500],relative))
                    finally:db.execute('RELEASE parse_file')
            deleted=db.execute('SELECT COUNT(*) FROM files WHERE seen!=?',(run,)).fetchone()[0]
            db.execute('DELETE FROM files WHERE seen!=?',(run,))
            resolver_complete=True
            if changed or deleted or force:
                resolver_complete=self.link(db)
            sha=hashlib.sha256((EXTRACTOR_VERSION+self.settings.digest()).encode())
            for row in db.execute('SELECT path,hash,status FROM files ORDER BY path'):
                sha.update(json.dumps(tuple(row),ensure_ascii=True,separators=(',',':')).encode())
                sha.update(b'\n')
            snapshot=sha.hexdigest()
            generation=Store.get(db,'generation',0)+(snapshot!=old_snapshot)
            stats={'snapshot':snapshot,'generation':generation,'parsed_files':parsed,
                   'changed_files':changed,'unchanged_files':unchanged,'deleted_files':deleted,
                   'seconds':round(time.monotonic()-started,6),'resolver_complete':resolver_complete}
            Store.set(db,'snapshot',snapshot);Store.set(db,'generation',generation)
            Store.set(db,'extractor_version',EXTRACTOR_VERSION)
            Store.set(db,'config_hash',self.settings.digest());Store.set(db,'last_index',stats)
            Store.set(db,'indexed_at',time.time())
        return stats

    def link(self,db):
        db.execute('DELETE FROM names')
        db.execute('INSERT INTO names SELECT qualified_name,id FROM symbols')
        complete=False
        for _ in range(64):
            cursor=db.execute('''INSERT OR IGNORE INTO names
                SELECT aliases.name,names.symbol FROM aliases JOIN names ON aliases.target=names.name''')
            if cursor.rowcount==0:complete=True;break
        db.execute('DELETE FROM call_targets')
        db.execute('''INSERT OR IGNORE INTO call_targets
            SELECT calls.id,names.symbol FROM calls JOIN names ON calls.hint=names.name''')
        # Prefer a concrete submodule for `from package import submodule`.
        db.execute('UPDATE imports SET target_file=NULL')
        db.execute('''UPDATE imports SET target_file=(
            SELECT MIN(path) FROM files WHERE language='python'
            AND module=imports.module||'.'||imports.imported
            HAVING COUNT(*)=1) WHERE imported IS NOT NULL''')
        db.execute('''UPDATE imports SET target_file=(
            SELECT MIN(path) FROM files WHERE language='python' AND module=imports.module
            HAVING COUNT(*)=1) WHERE target_file IS NULL''')
        return complete
