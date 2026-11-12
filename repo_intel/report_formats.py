"""Normalize documented output contracts, retaining uncertainty and coordinates."""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urlparse

from .json_stream import JsonStream, json_lines

FORMATS = ('jscpd', 'ast-grep', 'ast-grep-jsonl', 'pyspector', 'sarif', 'viztracer', 'tach-map', 'tach')


def positive(value, default=1):
    value = default if value is None else value
    if type(value) is not int or value<1:
        raise ValueError('Source lines must be positive integers')
    return value


def uri_path(value):
    if not isinstance(value, str) or not value or len(value)>16384:
        raise ValueError('Invalid report path')
    uri = urlparse(value)
    if uri.scheme == 'file':
        if uri.netloc not in ('', 'localhost'):
            raise ValueError('Remote file URI rejected')
        return unquote(uri.path)
    if '://' in value:
        raise ValueError('Remote source URI rejected')
    return unquote(value)


def normalize(kind, item):
    if not isinstance(item, dict):
        raise ValueError('Expected a JSON object record')
    if kind == 'tach-map':
        return dict(kind='dependency', rule='module-dependency', file=uri_path(item['from']),
                    related_file=uri_path(item['to']), line=None, end_line=None, related_line=None,
                    message='Tach file dependency', details={'source_line_available':False})
    if kind == 'tach':
        return dict(kind='architecture', rule=str(item['rule']),
                    file=uri_path(item['file']) if item.get('file') else None,
                    line=positive(item['line']) if item.get('line') else None,
                    message=str(item['message']), details={k:item[k] for k in
                        ('usage_module','definition_module','severity') if k in item})
    if kind == 'jscpd':
        a, b = item['firstFile'], item['secondFile']
        first = (uri_path(a['name']), positive(a['start']), positive(a['end']))
        second = (uri_path(b['name']), positive(b['start']), positive(b['end']))
        first, second = sorted((first, second))
        detail = {k:item[k] for k in ('format','tokens','lines','kind','similarity','method') if k in item}
        detail['related_end_line'] = second[2]
        return dict(kind='duplication', rule='clone', file=first[0], line=first[1], end_line=first[2],
                    related_file=second[0], related_line=second[1], message='Duplicate/similar block candidate', details=detail)
    if kind.startswith('ast-grep'):
        start, end = item['range']['start'], item['range']['end']
        if any(type(p.get('line')) is not int or p['line']<0 for p in (start,end)):
            raise ValueError('ast-grep lines must be nonnegative integers')
        return dict(kind='pattern', rule=str(item.get('ruleId','structural-match')), file=uri_path(item['file']),
                    line=start['line']+1, end_line=end['line']+1, message=str(item.get('message','Structural match')),
                    details={'column_zero_based':start.get('column'), 'end_column_zero_based':end.get('column'),
                             'end_exclusive':True, 'severity':item.get('severity')})
    if kind == 'pyspector':
        return dict(kind='security', rule=str(item['rule_id']), file=uri_path(item['file_path']),
                    line=positive(item['line_number']), message=str(item['description']),
                    details={k:item[k] for k in ('severity','cwe','remediation') if k in item})
    if kind == 'sarif':
        locations = item.get('locations', [])
        loc = locations[0].get('physicalLocation',{}) if locations else {}
        artifact, region = loc.get('artifactLocation',{}), loc.get('region',{})
        if not artifact.get('uri'):
            raise ValueError('SARIF result has no explicit artifact URI; indexed artifact references are not resolved')
        # Keep data-flow paths. Do not copy source snippets or fixes into the database.
        return dict(kind='security', rule=str(item.get('ruleId','unspecified')),
                    file=uri_path(artifact['uri']), line=positive(region.get('startLine')),
                    end_line=positive(region.get('endLine'), positive(region.get('startLine'))),
                    message=str(item.get('message',{}).get('text','Finding')),
                    details={'level':item.get('level'), 'codeFlows':item.get('codeFlows',[]),
                             'relatedLocations':item.get('relatedLocations',[]),
                             'properties':item.get('properties',{}), 'column_one_based':region.get('startColumn'),
                             'uriBaseId':artifact.get('uriBaseId')})
    raise ValueError(f'Unsupported record format {kind}')


class ReportReader:
    def __init__(self, kind, source):
        if kind not in FORMATS:
            raise ValueError(f'Unknown report format {kind}; choose {FORMATS}')
        self.kind, self.source = kind, source
        self.metadata = {}

    def __iter__(self):
        kind = self.kind
        if kind in ('ast-grep-jsonl','tach'):
            yield from json_lines(self.source)
            return
        paths = {
            'jscpd':[('duplicates','*')],
            'tach-map':[('*','*')],
            'ast-grep':[('*',)],
            'pyspector':[('issues','*')],
            'sarif':[('version',),('runs','*','tool'),('runs','*','invocations'),('runs','*','results','*')],
            'viztracer':[('traceEvents','*'),('viztracer_metadata',)]}[kind]
        stream = JsonStream(self.source, paths)
        for path, value in stream:
            if kind == 'tach-map':
                if len(path)!=2 or not isinstance(path[1],int) or not isinstance(value,str):
                    raise ValueError('Tach map must map file paths to arrays of file paths')
                yield {'from':path[0], 'to':value}
            elif kind == 'sarif' and (path == ('version',) or path[-1] in ('tool','invocations')):
                self.metadata['/'.join(map(str,path))] = value
            elif kind == 'viztracer' and path == ('viztracer_metadata',):
                self.metadata.update(value)
            else:
                yield value
        required = {'jscpd':('duplicates',),'pyspector':('issues',),'sarif':('runs',),
                    'ast-grep':(), 'tach-map':(), 'viztracer':('traceEvents',)}[kind]
        if required not in stream.containers:
            raise ValueError(f'Report schema mismatch: missing {required}')
        if kind == 'sarif' and self.metadata.get('version') != '2.1.0':
            raise ValueError('Only SARIF 2.1.0 is supported')


VIZ_NAME = re.compile(r'^(.*?)\s*\((.*):(\d+)\)$')


def trace_record(item):
    if item.get('ph') not in ('X','B','E'):
        return None
    match = VIZ_NAME.match(str(item.get('name','')))
    if not match:
        return None
    return {'file':uri_path(match[2]), 'line':positive(int(match[3])), 'qualname':match[1].rstrip(),
            'pid':item.get('pid'), 'tid':item.get('tid'), 'timestamp_ns':int(float(item['ts'])*1000),
            'event':{'X':'complete','B':'call','E':'return'}[item['ph']],
            'details':{'duration_ns':int(float(item.get('dur',0))*1000),
                       'source':'viztracer', 'caller_unknown':True, 'test_context_unknown':True}}
