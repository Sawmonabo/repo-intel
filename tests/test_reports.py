"""Upstream schema fixtures, not claims of upstream analyzer execution."""
import json
from pathlib import Path

import pytest

from repo_intel.service import Repository


def fixture(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'a.py').write_text('def first(x):\n    return x + 1\n\ndef second(y):\n    return y + 1\n')
    repo = Repository(root, tmp_path / 'state')
    repo.index()
    return repo


def report(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_stream_large_array_and_reject_trailing_garbage(tmp_path):
    from repo_intel.json_stream import JsonStream
    path = report(tmp_path, 'x.json', {'duplicates': [{'i': i} for i in range(20000)]})
    with path.open() as source:
        reader = JsonStream(source, [('duplicates', '*')], chunk_size=71)
        assert sum(item['i'] for _, item in reader) == sum(range(20000))
        assert reader.peak_buffer < 1024
    path.write_text('[1,2] trailing')
    with path.open() as source:
        with pytest.raises(ValueError):
            list(JsonStream(source, [('*',)]))


def test_stream_oversized_record_and_invalid_document(tmp_path):
    from repo_intel.json_stream import JsonStream
    for content in ['{"x":[{"s":"' + 'a'*10000 + '"}]}', '{"x":[1,]}', '{"x":NaN}']:
        path = tmp_path / 'bad.json'
        path.write_text(content)
        with path.open() as source, pytest.raises(ValueError):
            list(JsonStream(source, [('x', '*')], max_item=1024))


def test_jscpd_merge_is_idempotent_and_keeps_provenance(tmp_path):
    repo = fixture(tmp_path)
    path = report(tmp_path, 'cpd.json', {'duplicates': [
        {'format': 'python', 'lines': 2, 'tokens': 10, 'kind': 'exact',
         'firstFile': {'name': 'a.py', 'start': 1, 'end': 2},
         'secondFile': {'name': 'a.py', 'start': 4, 'end': 5}}
    ]})
    result = repo.import_report('jscpd', path)
    assert result['status'] == 'unverified_source_identity'
    assert result['accepted'] == 1
    assert repo.import_report('jscpd', path)['status'] == 'already_imported'
    rows = repo.query('findings')['items']
    assert len(rows) == 1
    assert rows[0]['file'] == 'a.py' and rows[0]['related_line'] == 4
    assert rows[0]['line'] == 1
    (repo.root / 'a.py').write_text('# different\n')
    repo.index()
    assert repo.query('findings')['items'] == []


def test_ast_grep_zero_based_positions_and_path_escape(tmp_path):
    repo = fixture(tmp_path)
    path = report(tmp_path, 'sg.json', [
        {'file': 'a.py', 'ruleId': 'no-plus-one', 'range': {
            'start': {'line': 1, 'column': 4}, 'end': {'line': 1, 'column': 16}},
         'message': 'candidate'}])
    repo.import_report('ast-grep', path)
    item = repo.query('findings')['items'][0]
    assert item['line'] == 2
    data = json.loads(item['details'])
    assert data['column_zero_based'] == 4
    bad = report(tmp_path, 'bad.json', [{'file': '../outside.py', 'range': {
        'start': {'line': 0, 'column': 0}, 'end': {'line': 1, 'column': 0}}}])
    rejected = repo.import_report('ast-grep', bad)
    assert rejected['accepted'] == 0 and rejected['rejected'] == 1


def test_sarif_preserves_paths_and_partial_metadata(tmp_path):
    repo = fixture(tmp_path)
    path = report(tmp_path, 'security.sarif', {'version': '2.1.0', 'runs': [{
        'tool': {'driver': {'name': 'PyFlow', 'version': 'fixture'}},
        'results': [{'ruleId': 'taint', 'level': 'warning', 'message': {'text': 'Potential flow'},
                     'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'a.py'},
                                                          'region': {'startLine': 2}}}],
                     'codeFlows': [{'threadFlows': [{'locations': []}]}]}]}]})
    repo.import_report('sarif', path)
    found = repo.query('findings')['items'][0]
    assert found['rule'] == 'taint' and found['line'] == 2
    assert json.loads(found['details'])['codeFlows']
    assert found['producer'] == 'sarif'


def test_pyspector_native_json(tmp_path):
    repo = fixture(tmp_path)
    path = report(tmp_path, 'security.json', {'summary': {'issue_count': 1}, 'issues': [
        {'rule_id': 'TEST', 'file_path': str(repo.root / 'a.py'), 'line_number': 2,
         'description': 'Candidate', 'severity': 'HIGH', 'cwe': 'CWE-20', 'code': 'secret excluded'}]})
    repo.import_report('pyspector', path)
    item = repo.query('findings')['items'][0]
    assert item['rule'] == 'TEST' and 'secret excluded' not in item['details']


def test_viztracer_overflow_unknown_callsite_and_verified_manifest(tmp_path):
    repo = fixture(tmp_path)
    path = report(tmp_path, 'trace.json', {'traceEvents': [
        {'ph': 'X', 'name': f'first ({repo.root}/a.py:1)', 'pid': 1, 'tid': 2, 'ts': 1.25, 'dur': 3.5}],
        'viztracer_metadata': {'overflow': True, 'version': 'fixture'}})
    manifest = repo.export_manifest()
    imported = repo.import_report('viztracer', path, manifest=manifest)
    assert imported['status'] == 'partial'
    event = repo.query('runtime')['items'][0]
    assert event['timestamp_ns'] == 1250 and event['caller_line'] is None
    assert json.loads(event['details'])['duration_ns'] == 3500


def test_report_failure_rolls_back_and_wrong_source_manifest_is_rejected(tmp_path):
    repo = fixture(tmp_path)
    path = tmp_path / 'bad.json'
    path.write_text('{"duplicates":[{"firstFile":{"name":"a.py","start":1,"end":2},"secondFile":{"name":"a.py","start":4,"end":5}},')
    with pytest.raises(ValueError):
        repo.import_report('jscpd', path)
    assert repo.query('runs')['items'] == []
    good = report(tmp_path, 'good.json', {'duplicates': []})
    manifest = repo.export_manifest()
    manifest['snapshot'] = 'incorrect'
    with pytest.raises(ValueError, match='snapshot'):
        repo.import_report('jscpd', good, manifest=manifest)


@pytest.mark.parametrize('first_end,second_end',[(999,5),(2,999)])
def test_report_ranges_cannot_extend_beyond_source(tmp_path,first_end,second_end):
    repo=fixture(tmp_path)
    path=report(tmp_path,'ranges.json',{'duplicates':[{
        'firstFile':{'name':'a.py','start':1,'end':first_end},
        'secondFile':{'name':'a.py','start':4,'end':second_end}}]})
    result=repo.import_report('jscpd',path,manifest=repo.export_manifest())
    assert result['accepted']==0 and result['rejected']==1
    assert repo.query('findings')['items']==[]
