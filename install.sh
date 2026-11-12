#!/usr/bin/env sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$BASE/install.py" "$@"
