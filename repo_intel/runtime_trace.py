from __future__ import annotations

import contextvars
import functools
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

CONTEXT=contextvars.ContextVar('repo_intel_test_context',default='')
COVERAGE=None


class TraceWriter:
    """Streaming Python profile events. No values, locals or function arguments captured."""
    def __init__(self,root: Path,path: Path,max_events=1000000,max_bytes=256*1024*1024):
        self.root=root.resolve();self.path=path;self.max_events=max_events;self.max_bytes=max_bytes
        self.events=0;self.dropped=0;self.bytes=0;self.file_hashes={};self.lock=threading.Lock()
        self.out=None;self.previous=None;self.previous_thread=None;self.active=False

    @functools.lru_cache(maxsize=8192)
    def locate(self,filename):
        if not filename or filename.startswith('<'):return None
        path=Path(filename).resolve()
        if not path.is_relative_to(self.root):return None
        try:
            relative=path.relative_to(self.root).as_posix()
            if relative not in self.file_hashes:
                sha=hashlib.sha256()
                with path.open('rb') as source:
                    while chunk:=source.read(65536):sha.update(chunk)
                self.file_hashes[relative]=sha.hexdigest()
            return relative
        except OSError:return None

    def profile(self,frame,event,arg):
        if not self.active or event not in ('call','return'):return
        filename=self.locate(frame.f_code.co_filename)
        if filename is None:return
        with self.lock:
            if not self.active:return
            if self.events>=self.max_events or self.bytes>=self.max_bytes:
                self.dropped+=1;return
            parent=frame.f_back
            caller=self.locate(parent.f_code.co_filename) if parent else None
            record={'seq':self.events,'pid':os.getpid(),'tid':threading.get_ident(),
                'timestamp_ns':time.perf_counter_ns(),'event':event,'file':filename,
                'line':frame.f_code.co_firstlineno,'qualname':frame.f_code.co_qualname,
                'caller_file':caller,'caller_line':parent.f_lineno if caller else None,
                'test':CONTEXT.get()}
            encoded=(json.dumps(record,separators=(',',':'),ensure_ascii=True)+'\n').encode('utf-8')
            if self.bytes+len(encoded)>self.max_bytes:self.dropped+=1;return
            self.out.write(encoded);self.events+=1;self.bytes+=len(encoded)

    def start(self):
        if sys.getprofile() is not None:raise RuntimeError('Another profiler is installed; refusing to replace it')
        self.out=self.path.open('wb',buffering=65536)
        self.previous=sys.getprofile();self.previous_thread=threading.getprofile()
        self.active=True
        threading.setprofile(self.profile);sys.setprofile(self.profile)

    def stop(self):
        sys.setprofile(self.previous);threading.setprofile(self.previous_thread)
        with self.lock:
            self.active=False
            if self.out:self.out.flush();self.out.close()
        return {'events':self.events,'dropped_events':self.dropped,'bytes':self.bytes,
                'trace_complete':self.dropped==0,'file_hashes':self.file_hashes,
                'limits':{'max_events':self.max_events,'max_bytes':self.max_bytes},
                'limitations':['Python profile events only; C calls omitted',
                    'Child processes are not automatically instrumented',
                    'Threads without propagated ContextVar have no test attribution',
                    'Generator/coroutine return events can be suspension, not final completion']}
