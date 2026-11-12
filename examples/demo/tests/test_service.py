import pytest
from acme.service import calculate, normalize


def test_normalized_length():
    assert calculate('  Example  ')==7


def test_legacy_branch():
    assert normalize('legacy')=='standard'


@pytest.mark.skip(reason='Intentional skipped-test detection fixture')
def test_intentional_skip():
    assert calculate('x')==1
