#!/bin/sh
set -eu
sh /opt/build/resolve-artifact.sh org.aksw.data.faostat faostat-qcl-2025-duckdb \
    "$FAOSTAT_VERSION" duckdb.zst faostat.duckdb.zst
sh /opt/build/resolve-artifact.sh org.duckdb duckdb_jdbc \
    "$DUCKDB_JDBC_VERSION" jar duckdb_jdbc.jar
