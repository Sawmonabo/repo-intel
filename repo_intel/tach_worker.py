"""Optional Tach Python-extension bridge; executed only through the trusted worker.

Contract checked against python/tach/extension.pyi. No dependency is imported by
normal RepoIntel indexing, querying, or MCP startup.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    from tach import extension
    root=args.root.resolve()
    if (root/'tach.toml').exists():
        config,_=extension.parse_project_config(root/'tach.toml')
    elif (root/'pyproject.toml').exists():
        config=extension.parse_project_config_from_pyproject(root/'pyproject.toml')
    else:
        raise ValueError('Tach requires an existing tach.toml or pyproject.toml configuration; no architecture is invented')
    diagnostics=extension.check(root,config,True,True)
    with args.output.open('w',encoding='utf-8') as output:
        for diagnostic in diagnostics:
            rule='configuration' if diagnostic.is_configuration() else (
                'dependency' if diagnostic.is_dependency_error() else (
                'interface' if diagnostic.is_interface_error() else 'diagnostic'))
            output.write(json.dumps({'rule':rule, 'file':diagnostic.pyfile_path(),
                'line':diagnostic.pyline_number(),'message':diagnostic.to_string(),
                'usage_module':diagnostic.usage_module(),'definition_module':diagnostic.definition_module(),
                'severity':'error' if diagnostic.is_error() else 'warning'})+'\n')
    print(json.dumps({'diagnostics':len(diagnostics),'version':importlib.metadata.version('tach')}))


if __name__=='__main__':
    main()
