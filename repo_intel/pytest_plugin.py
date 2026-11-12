"""Loaded explicitly by the capture runner, never auto-enabled in user projects."""
import pytest
from . import runtime_trace


def phase(item,name):
    value=item.nodeid+'|'+name
    token=runtime_trace.CONTEXT.set(value)
    if runtime_trace.COVERAGE:runtime_trace.COVERAGE.switch_context(value)
    return token


def reset(token):
    runtime_trace.CONTEXT.reset(token)
    if runtime_trace.COVERAGE:runtime_trace.COVERAGE.switch_context('')


@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_setup(item):
    token=phase(item,'setup')
    try:yield
    finally:reset(token)


@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_call(item):
    token=phase(item,'call')
    try:yield
    finally:reset(token)


@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_teardown(item,nextitem):
    token=phase(item,'teardown')
    try:yield
    finally:reset(token)
