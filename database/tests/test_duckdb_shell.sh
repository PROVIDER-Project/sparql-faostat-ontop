#!/bin/sh
# Run against a locally built image; no dataset or existing database is touched.
set -eu
image=${1:-aksw/duckdb-shell:1.5.6}
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker run --rm "$image" --version | grep -F 'v1.5.6'
docker run --rm -i --entrypoint /bin/sh \
    --mount "type=bind,src=$repo/loader,dst=/opt/loader,readonly" \
    "$image" -s <<'SMOKE'
set -eu
printf 'CREATE OR REPLACE TABLE smoke AS SELECT 42 AS value;\n' > /tmp/load.sql
sh /opt/loader/load-duckdb.sh /tmp/test.duckdb /tmp/load.sql
test -f /tmp/test.duckdb.complete
# Missing SQL proves that the second run skips opening the database.
sh /opt/loader/load-duckdb.sh /tmp/test.duckdb /tmp/missing.sql
rm /tmp/test.duckdb.complete
printf 'SELECT * FROM missing_table;\n' > /tmp/fail.sql
if sh /opt/loader/load-duckdb.sh /tmp/test.duckdb /tmp/fail.sql; then
    echo 'Expected SQL failure' >&2
    exit 1
fi
test ! -e /tmp/test.duckdb.complete
sh /opt/loader/load-duckdb.sh /tmp/test.duckdb /tmp/load.sql
test -f /tmp/test.duckdb.complete
duckdb /tmp/test.duckdb -csv -noheader -c 'SELECT value FROM smoke' | grep -x 42
SMOKE
