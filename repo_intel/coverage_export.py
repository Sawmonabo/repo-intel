"""Runs only in the test interpreter. Core imports normalized JSONL, not coverage internals."""
from __future__ import annotations

import json
from pathlib import Path


def export(data, root: Path, output: Path, max_bytes: int):
    rows=size=0
    complete=True
    with output.open('wb',buffering=65536) as sink:
        def emit(record):
            nonlocal rows,size,complete
            encoded=(json.dumps(record,separators=(',',':'),ensure_ascii=True)+'\n').encode()
            if size+len(encoded)>max_bytes:
                complete=False
                return False
            sink.write(encoded);size+=len(encoded);rows+=1
            return True
        for filename in sorted(data.measured_files()):
            full=Path(filename).resolve()
            if not full.is_relative_to(root):continue
            relative=full.relative_to(root).as_posix()
            data.set_query_contexts(None)
            contexts=set()
            for line,names in data.contexts_by_lineno(filename).items():
                for context in names:
                    if not context:continue
                    contexts.add(context)
                    if not emit({'kind':'line','file':relative,'test':context,'line':line}):break
                if not complete:break
            if not complete:break
            if data.has_arcs():
                for context in sorted(contexts):
                    data.set_query_context(context)
                    for source,target in data.arcs(filename) or []:
                        if not emit({'kind':'arc','file':relative,'test':context,'source':source,'target':target}):break
                    if not complete:break
            if not complete:break
    return {'coverage_complete':complete,'coverage_rows':rows,'coverage_bytes':size,
            'coverage_budget_bytes':max_bytes}
