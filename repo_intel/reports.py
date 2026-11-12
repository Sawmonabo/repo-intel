"""Atomic import of bounded specialist reports into the canonical evidence store."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .config import identity, safe_path
from .report_formats import FORMATS, ReportReader, normalize, trace_record
from .storage import Store


def file_digest(path: Path):
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class Reports:
    def __init__(self, repo):
        self.repo = repo

    def manifest(self):
        with self.repo.store.read() as db:
            return {'schema':1, 'root':str(self.repo.root), 'snapshot':Store.get(db,'snapshot'),
                    'created':time.time(), 'meaning':'Declared source snapshot; not proof an external tool analyzed it'}

    def _path(self, db, value):
        full=safe_path(self.repo.root,value)
        relative=full.relative_to(self.repo.root).as_posix()
        row=db.execute('SELECT status,lines FROM files WHERE path=?',(relative,)).fetchone()
        if not row or row['status']!='ok':
            raise ValueError('Report location not successfully indexed')
        return relative, row['lines']

    def ingest(self, kind: str, path: Path, *, manifest=None, version='unknown', max_report_bytes=1024**3):
        if kind not in FORMATS:
            raise ValueError(f'Unsupported report format: {kind}')
        path=Path(path).resolve()
        if not path.is_file() or path.stat().st_size>max_report_bytes:
            raise ValueError('Report missing or larger than report budget')
        content=file_digest(path)
        accepted=rejected=0
        reasons={}
        with self.repo.store.write() as db:
            snapshot=Store.get(db,'snapshot')
            if not snapshot:
                raise ValueError('Index the repository before importing reports')
            if manifest:
                if manifest.get('root')!=str(self.repo.root) or manifest.get('snapshot')!=snapshot:
                    raise ValueError('Report manifest source snapshot does not match the current repository index')
            run=identity(snapshot,kind,content,manifest or {},version)
            if db.execute('SELECT 1 FROM runs WHERE id=?',(run,)).fetchone():
                return {'status':'already_imported','run':run}
            status='complete' if manifest else 'unverified_source_identity'
            if manifest and manifest.get('execution',{}).get('exit_code',0)!=0:
                status='partial'
            provenance={'report_sha256':content, 'source_identity':'declared_snapshot' if manifest else 'unverified',
                        'upstream_execution_verified_by_this_package':bool(manifest and manifest.get('upstream_execution_observed')),
                        'manifest':manifest, 'report_format':kind, 'scope_complete':None}
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',
                       (run,snapshot,'report',kind,version,status,time.time(),json.dumps(provenance)))
            with path.open(encoding='utf-8') as source:
                reader=ReportReader(kind,source)
                for item in reader:
                    try:
                        if kind=='viztracer':
                            event=trace_record(item)
                            if event is None:
                                rejected+=1;reasons['non_source_event']=reasons.get('non_source_event',0)+1
                                continue
                            relative,lines=self._path(db,event['file'])
                            if event['line']>lines:
                                raise ValueError('Trace source line outside indexed file')
                            db.execute('INSERT INTO runtime_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (run,accepted,event['pid'],event['tid'],event['timestamp_ns'],event['event'],relative,
                                 event['line'],event['qualname'],None,None,'',json.dumps(event['details'])))
                        else:
                            row=normalize(kind,item)
                            lines=None
                            if row['file'] is not None:
                                row['file'],lines=self._path(db,row['file'])
                            if row['line'] is not None and lines is not None and row['line']>lines:
                                raise ValueError('Report source line outside indexed file')
                            if row.get('related_file'):
                                row['related_file'],other_lines=self._path(db,row['related_file'])
                                if row.get('related_line') is not None and row['related_line']>other_lines:
                                    raise ValueError('Related source line outside indexed file')
                                related_end=row['details'].get('related_end_line')
                                if related_end is not None and (related_end>other_lines or related_end<row['related_line']):
                                    raise ValueError('Related source range outside indexed file')
                            row.setdefault('end_line',row['line'])
                            if row['line'] is not None and row['end_line'] is not None and row['end_line']<row['line']:
                                raise ValueError('Invalid source range')
                            if lines is not None and row['end_line'] is not None:
                                exclusive_next_line=kind.startswith('ast-grep') and row['details'].get('end_column_zero_based')==0
                                if row['end_line']>lines+int(exclusive_next_line):
                                    raise ValueError('Source range outside indexed file')
                            # Identity includes semantic rule and coordinates; different tools
                            # are not assumed equivalent merely because they share a location.
                            key=identity(snapshot,row['kind'],row['rule'],row['file'],row['line'],row['end_line'],
                                         row.get('related_file'),row.get('related_line'))
                            db.execute('INSERT OR IGNORE INTO findings VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (key,row['kind'],row['rule'],row['file'],row['line'],row['end_line'],
                                 row.get('related_file'),row.get('related_line'),row['message'][:16384],json.dumps(row['details'])))
                            evidence={'normalizer':'repo-intel', 'source_identity':provenance['source_identity'],
                                      'record_sha256':identity(item), 'details':row['details']}
                            db.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?,?)',
                                       (identity(run,key),key,run,json.dumps(evidence)))
                        accepted+=1
                    except (KeyError, TypeError, ValueError, OverflowError) as exc:
                        rejected+=1
                        reason=str(exc)[:150]
                        if len(reasons)<32 or reason in reasons:
                            reasons[reason]=reasons.get(reason,0)+1
                provenance['upstream_metadata']=reader.metadata
                provenance['accepted']=accepted
                provenance['rejected']=rejected
                provenance['rejection_reasons']=reasons
                if kind=='viztracer':
                    provenance['trace_complete']=None if 'overflow' not in reader.metadata else not reader.metadata['overflow']
                    if reader.metadata.get('overflow'):
                        status='partial'
                if rejected and status=='complete':
                    status='partial'
                # Diagnostics may carry explicit solver incompleteness. Do not promote
                # an external report to complete program analysis based on exit code.
                if kind=='sarif':
                    provenance['scope_complete']=None
                db.execute('UPDATE runs SET status=?,manifest=? WHERE id=?',(status,json.dumps(provenance),run))
        return {'run':run,'status':status,'accepted':accepted,'rejected':rejected,
                'rejection_reasons':reasons,'scope_complete':None}
