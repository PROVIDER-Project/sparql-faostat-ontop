#!/bin/sh
set -eu

database=${1:-/workspace/faostat.duckdb}
load_sql=${2:-/opt/ontop/input/load.sql}
marker="${database}.complete"

if [ -f "$marker" ] && [ -s "$database" ]; then
    echo "load: already complete ($database); skipping"
    exit 0
fi

# A marker without a usable database must not survive an unsuccessful reload.
rm -f "$marker"
echo "load: building $database"
duckdb "$database" -bail -f "$load_sql"

if [ ! -s "$database" ]; then
    echo "load: DuckDB exited successfully but no nonempty database was created" >&2
    exit 1
fi

# DuckDB has committed and closed the database before it is marked complete.
: > "$marker"
echo "load: complete ($marker)"
