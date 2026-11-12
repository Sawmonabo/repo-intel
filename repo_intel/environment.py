"""Runtime dependency diagnostics. Distribution backports require operator verification."""
from __future__ import annotations
import sqlite3


def sqlite_safety(version=None):
    value=tuple(version or sqlite3.sqlite_version_info)
    fixed=value>=(3,51,3) or ((3,44,6)<=value<(3,45,0)) or ((3,50,7)<=value<(3,51,0))
    return {'version':'.'.join(map(str,value)),'known_wal_reset_fix':fixed,
            'warning':None if fixed else 'SQLite version predates the published WAL-reset fix or an identified backport. Use a patched Python/SQLite build for production; vendor backports cannot be inferred from version alone.',
            'source':'https://www.sqlite.org/wal.html#the_wal_reset_bug',
            'application_writer_serialization':True}
