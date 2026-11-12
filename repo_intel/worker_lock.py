"""One heavyweight subprocess per repository, across independent CLI clients."""
from __future__ import annotations

import os
from pathlib import Path


class WorkerLock:
    def __init__(self, state: Path, filename='worker.lock'):
        if filename not in ('worker.lock','database-writer.lock'):
            raise ValueError('Unknown lock purpose')
        self.path=state/filename
        self.file=None

    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.is_symlink():
            raise ValueError('Worker lock must not be a symlink')
        self.file=self.path.open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,BlockingIOError) as exc:
            self.file.close();self.file=None
            raise ValueError('Another analysis worker is active for this repository; retry after it exits') from exc
        return self

    def __exit__(self,exc_type,exc,tb):
        if self.file:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close();self.file=None
