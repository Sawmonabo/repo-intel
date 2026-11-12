import pytest
from repo_intel.service import Repository


def make(tmp_path, content):
    root = tmp_path / 'p'; root.mkdir()
    (root / 'a.py').write_text(content)
    repo = Repository(root, tmp_path / 'state'); repo.index()
    return repo


def test_flow_branches_merge_reaching_definitions(tmp_path):
    repo = make(tmp_path, 'def f(flag, x):\n    y = x\n    if flag:\n        y = 42\n    return y\n')
    result = repo.flow('a.f')
    nodes = {x['id']: x for x in result['nodes']}
    target = next(x['id'] for x in result['nodes'] if x['line'] == 5)
    defs = [edge for edge in result['data_edges'] if edge['to'] == target and edge['name'] == 'y']
    assert {nodes[x['from']]['line'] for x in defs} == {2, 4}
    assert {'true','false'} <= {e['kind'] for e in result['control_edges']}
    assert result['analysis_complete'] is True
    assert result['scope'] == 'statement_level_normal_control_flow_and_lexical_values'


def test_loop_fixedpoint_and_local_call_arguments(tmp_path):
    repo = make(tmp_path, 'def callee(x):\n    return x\n\ndef loop(xs):\n    total = 0\n    for x in xs:\n        total += x\n    return callee(total)\n')
    result = repo.flow('a.loop')
    assert any(e['kind'] == 'loop' for e in result['control_edges'])
    site = result['call_sites'][0]
    assert site['target_name'] == 'a.callee'
    assert site['actual_arguments']['positional'] == ['total']
    assert site['formal_parameter_names'] == ['x']
    assert 'argument_expressions_not_alias_proof' in site['limitations']


def test_unsupported_exception_flow_is_explicit_and_budgets_reject(tmp_path):
    repo = make(tmp_path, 'def f(x):\n    try:\n        return x()\n    finally:\n        print("done")\n')
    result = repo.flow('a.f')
    assert result['analysis_complete'] is False
    assert 'Try' in result['unsupported_constructs']
    with pytest.raises(ValueError):
        repo.flow('a.f', max_nodes=0)
    (repo.root/'a.py').write_text('# stale\n')
    with pytest.raises(ValueError, match='stale'):
        repo.flow('a.f')


def test_flow_does_not_treat_nested_function_body_as_executed(tmp_path):
    repo = make(tmp_path, 'def f(x):\n    def inner():\n        secret = x\n        return secret\n    return inner\n')
    result = repo.flow('a.f')
    assert not any('secret' in n['uses'] or 'secret' in n['defs'] for n in result['nodes'])
