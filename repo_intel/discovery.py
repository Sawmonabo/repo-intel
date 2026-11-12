from __future__ import annotations

import os
import subprocess
from pathlib import Path
from .config import Settings

TEXT_EXTENSIONS = {'.py','.pyi','.md','.txt','.toml','.yaml','.yml','.json','.ini','.cfg','.rst',
                   '.js','.ts','.tsx','.jsx','.rs','.go','.java','.c','.h','.cpp','.cs','.rb','.sh'}


def split_nul(stream):
    pending = b''
    while chunk := stream.read(65536):
        parts = (pending + chunk).split(b'\0')
        pending = parts.pop()
        for part in parts:
            yield os.fsdecode(part)
    if pending:
        yield os.fsdecode(pending)


def discover(root: Path, settings: Settings, state: Path):
    """Git supplies authoritative ignore behavior. Never follows directory symlinks."""
    try:
        check = subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],
                               stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        check = None
    if check is not None and check.returncode == 0:
        proc = subprocess.Popen(['git','-C',str(root),'ls-files','-c','-o','--exclude-standard','-z'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert proc.stdout
        try:
            for relative in split_nul(proc.stdout):
                path = root / relative
                if path.suffix.lower() in TEXT_EXTENSIONS and not settings.excluded(relative):
                    if not path.absolute().is_relative_to(state):
                        yield relative
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)
        if proc.returncode not in (0, -15):
            raise RuntimeError('git ls-files failed; discovery is incomplete')
        return
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if not (base/d).is_symlink()
                         and not settings.excluded((base/d).relative_to(root).as_posix())
                         and not (base/d).absolute().is_relative_to(state))
        for name in sorted(files):
            path = base/name
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() in TEXT_EXTENSIONS and not settings.excluded(relative):
                yield relative
