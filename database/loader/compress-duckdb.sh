#!/bin/sh
set -eu

input=${1:?Usage: compress-duckdb.sh INPUT OUTPUT [LEVEL] [THREADS]}
output=${2:?Usage: compress-duckdb.sh INPUT OUTPUT [LEVEL] [THREADS]}
level=${3:-6}
threads=${4:-2}
partial="${output}.part"

if [ ! -s "$input" ]; then
    echo "compress: input database is missing or empty: $input" >&2
    exit 1
fi
if [ "$input" = "$output" ]; then
    echo "compress: input and output must differ" >&2
    exit 1
fi

# Publish only a complete, checked archive. Preserve the database on failure.
trap 'rm -f "$partial"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

zstd --compress --check --threads="$threads" "-$level" --stdout -- "$input" > "$partial"
zstd --test -- "$partial"
test -s "$partial"
mv -f "$partial" "$output"
echo "compress: complete ($output)"
