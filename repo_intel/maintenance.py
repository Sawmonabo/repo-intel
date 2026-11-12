"""Explicit retention; never walks or deletes repository source."""
from __future__ import annotations

from .worker_lock import WorkerLock


class Maintenance:
    def __init__(self, repo):
        self.repo=repo

    def prune(self, *, keep_runs=10, drop_raw=False, apply=False):
        if type(keep_runs) is not int or not 0<=keep_runs<=1000000:
            raise ValueError('keep_runs must be 0..1000000')
        if type(drop_raw) is not bool or type(apply) is not bool:
            raise ValueError('drop_raw and apply must be booleans')
        count=raw_count=raw_bytes=0
        # The same gate prevents deleting a running collector's artifacts.
        with WorkerLock(self.repo.store.state):
            with self.repo.store.write() as db:
                count=db.execute('SELECT max(0,count(*)-?) FROM runs',(keep_runs,)).fetchone()[0]
                if apply:
                    db.execute('DELETE FROM runs WHERE id IN (SELECT id FROM runs ORDER BY created DESC,id LIMIT -1 OFFSET ?)',(keep_runs,))
                    db.execute('DELETE FROM findings WHERE NOT EXISTS(SELECT 1 FROM evidence WHERE evidence.finding=findings.id)')
            directory=self.repo.store.state/'runs'
            if drop_raw and directory.exists() and not directory.is_symlink():
                for child in directory.iterdir():
                    if child.is_symlink() or not child.is_dir():continue
                    for path in child.iterdir():
                        if path.is_symlink() or not path.is_file():continue
                        # Retain manifests and capped logs. Raw facts already live in SQLite.
                        if path.name in {'events.jsonl','coverage.db','coverage.jsonl','report.json','jscpd-report.json'}:
                            raw_count+=1;raw_bytes+=path.stat().st_size
                            if apply:path.unlink()
        return {'applied':apply,'runs_to_remove':count,'raw_files_to_remove':raw_count,
                'raw_bytes_to_remove':raw_bytes,'keep_runs':keep_runs,
                'notes':['No repository source is modified','SQLite reuses freed pages; file size does not shrink automatically',
                         'Manifests and process logs remain; failed-run raw artifacts are also removed when drop_raw is requested']}
