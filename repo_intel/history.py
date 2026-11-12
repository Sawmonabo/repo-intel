from __future__ import annotations

import re
import subprocess
import time
from .discovery import split_nul
from .storage import Store


class History:
    def __init__(self,store):self.store=store

    def collect(self,max_commits=5000):
        if type(max_commits) is not int or not 1<=max_commits<=1000000:raise ValueError('max_commits must be 1..1000000')
        root=str(self.store.root)
        head=subprocess.run(['git','-C',root,'rev-parse','HEAD'],capture_output=True,text=True,timeout=15)
        if head.returncode:raise ValueError('Git history requires at least one commit')
        total=subprocess.run(['git','-C',root,'rev-list','--count','HEAD'],capture_output=True,text=True,timeout=30)
        proc=subprocess.Popen(['git','-C',root,'log',f'-n{max_commits}','--format=%x1e%H%x09%ct',
            '--name-only','-z','--no-renames','--no-ext-diff','--relative','--','.'],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        count=membership=0;current=None;first_path=False
        try:
            with self.store.write() as db:
                db.execute('DELETE FROM commits')
                for token in split_nul(proc.stdout):
                    header=re.fullmatch(r'\x1e([a-f0-9]{40,64})\t(\d+)\n?',token)
                    if header:
                        current=header.group(1);first_path=True;count+=1
                        db.execute('INSERT OR IGNORE INTO commits VALUES(?,?)',(current,int(header.group(2))))
                        continue
                    if first_path:
                        token=token.removeprefix('\n');first_path=False
                    if token and current:
                        db.execute('INSERT OR IGNORE INTO commit_files VALUES(?,?)',(current,token));membership+=1
                code=proc.wait(timeout=30)
                if code:raise RuntimeError('Git history collection failed')
                result={'commits':count,'memberships':membership,'head':head.stdout.strip(),
                    'max_commits':max_commits,'repository_commit_count':int(total.stdout.strip()) if total.returncode==0 else None,
                    'rename_tracking':False,'merge_semantics':'git log default name-only; merge commits may have no file membership',
                    'collected_at':time.time()}
                result['truncated']=result['repository_commit_count'] is None or result['repository_commit_count']>max_commits
                Store.set(db,'history_scope',result)
            return result
        finally:
            if proc.stdout:proc.stdout.close()
            if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
