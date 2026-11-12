#!/usr/bin/env python3
"""Install the bundled wheel offline into a dedicated environment. No global mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info<(3,11):
        raise SystemExit('RepoIntel needs Python 3.11+; use the same or newer grammar as the analyzed code.')
    base=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,default=base/'.venv',help='New dedicated virtual environment directory')
    args=parser.parse_args()
    target=args.prefix.expanduser().absolute()
    if target.exists():
        raise SystemExit(f'Refusing to overwrite an existing path: {target}. Choose a new --prefix.')
    wheel=base/'wheels'/'repo_intel_local-0.1.0-py3-none-any.whl'
    if not wheel.is_file():raise SystemExit('Bundled wheel missing. Use the complete release ZIP.')
    hashes=json.loads((base/'wheels'/'SHA256.json').read_text())
    actual=hashlib.sha256(wheel.read_bytes()).hexdigest()
    if actual!=hashes.get(wheel.name):raise SystemExit('Bundled wheel checksum mismatch; refusing installation.')
    venv.EnvBuilder(with_pip=True,clear=False,system_site_packages=False).create(target)
    python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps','--disable-pip-version-check',str(wheel)],check=True)
    subprocess.run([str(python),'-m','repo_intel','--version'],check=True)
    print('\nInstalled without network access or model credentials.')
    print(f'Python: {python}')
    print('Next: use that Python with -m repo_intel --repo /absolute/path/to/repo index')
    print('See README.md for one shared MCP service and subscription-agent configuration.')


if __name__=='__main__':
    try:main()
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Installation failed: {exc}',file=sys.stderr)
        raise SystemExit(1)
