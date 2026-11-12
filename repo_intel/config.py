from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    source_roots: tuple[str, ...] = ('src', '.')
    exclude: tuple[str, ...] = ('.git', '.venv', 'venv', 'node_modules', '__pycache__',
                                'dist', 'build', '.tox', '.mypy_cache', '.pytest_cache')
    max_file_bytes: int = 8 * 1024 * 1024
    max_text_bytes: int = 2 * 1024 * 1024
    sqlite_cache_kib: int = 8192
    query_limit: int = 200
    max_query_rows: int = 2000
    max_graph_nodes: int = 10000
    query_timeout_seconds: float = 15.0
    clone_min_nodes: int = 12
    clone_max_tokens: int = 4096
    entrypoints: tuple[str, ...] = ()
    layers: tuple[dict, ...] = ()
    boundaries: tuple[dict, ...] = ()

    @classmethod
    def load(cls, root: Path) -> 'Settings':
        config = root / 'repo-intel.toml'
        if not config.exists():
            return cls()
        if config.is_symlink() or config.stat().st_size > 1024 * 1024:
            raise ValueError('Unsafe or oversized repo-intel.toml')
        raw = tomllib.loads(config.read_text(encoding='utf-8'))
        allowed = set(cls.__dataclass_fields__)
        extra = set(raw) - allowed
        if extra:
            raise ValueError(f'Unknown configuration fields: {sorted(extra)}')
        for name in ('source_roots', 'exclude', 'entrypoints', 'layers', 'boundaries'):
            if name in raw:
                if not isinstance(raw[name], list):
                    raise ValueError(f'{name} must be a TOML array')
                raw[name] = tuple(raw[name])
        result = cls(**raw)
        for name in ('max_file_bytes', 'max_text_bytes', 'sqlite_cache_kib', 'query_limit',
                     'max_query_rows', 'max_graph_nodes', 'clone_min_nodes', 'clone_max_tokens'):
            if type(getattr(result, name)) is not int or getattr(result, name) <= 0:
                raise ValueError(f'{name} must be a positive integer')
        if not 0 < result.query_timeout_seconds <= 3600:
            raise ValueError('query_timeout_seconds must be in (0, 3600]')
        for attr in ('source_roots','exclude','entrypoints'):
            if not all(isinstance(x,str) and x and '\x00' not in x for x in getattr(result,attr)):
                raise ValueError(f'{attr} must contain nonempty strings')
        for spec in result.layers:
            if not isinstance(spec,dict) or set(spec)-{'name','modules'}:
                raise ValueError('Each layer must contain only name and modules')
            if not isinstance(spec.get('name'),str) or not isinstance(spec.get('modules'),list) or not all(isinstance(x,str) and x for x in spec['modules']):
                raise ValueError('Layer name must be text and modules must be an array of nonempty strings')
        for spec in result.boundaries:
            if not isinstance(spec,dict) or set(spec)-{'from','deny'}:
                raise ValueError('Each boundary must contain only from and deny')
            if not isinstance(spec.get('from'),str) or not isinstance(spec.get('deny'),list) or not all(isinstance(x,str) and x for x in spec['deny']):
                raise ValueError('Boundary from must be text and deny must be an array of nonempty strings')
        for source in result.source_roots:
            safe_path(root, source)
        return result

    def digest(self) -> str:
        return digest(json.dumps(asdict(self), sort_keys=True))

    def excluded(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, p) or p in Path(path).parts for p in self.exclude)


def digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode('utf-8', 'surrogatepass')
    return hashlib.sha256(value).hexdigest()


def identity(*parts: object) -> str:
    return digest(json.dumps(parts, ensure_ascii=True, separators=(',', ':')))[:40]


def safe_path(root: Path, relative: str | Path) -> Path:
    """Resolve symlinks and reject all locations outside the configured worktree."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes repository: {relative}')
    return path


def default_state(root: Path) -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    return base / 'repo-intel' / digest(str(root.resolve()))[:24]


def module_name(path: str, settings: Settings) -> str:
    source = Path(path)
    roots = sorted(settings.source_roots, key=lambda x: len(Path(x).parts), reverse=True)
    for item in roots:
        candidate = Path(item)
        if source.is_relative_to(candidate):
            source = source.relative_to(candidate)
            break
    parts = list(source.with_suffix('').parts)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts) or '__root__'
