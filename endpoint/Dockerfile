# Download/extraction tools stay in this stage; only verified artifacts are copied.
ARG ENDPOINT_VERSION=0.0.1
ARG FAOSTAT_VERSION=0.0.1
ARG DUCKDB_JDBC_VERSION=1.5.6.0
FROM debian:bookworm-slim AS download-tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl zstd \
    && rm -rf /var/lib/apt/lists/*

# Independent stages: changing the driver does not invalidate the data download.
FROM download-tools AS database
ARG FAOSTAT_REPOSITORY_URL=https://maven.inf-ai.duckdns.org/releases
ARG FAOSTAT_VERSION
RUN set -eu; \
    mkdir -p /artifacts; \
    url="${FAOSTAT_REPOSITORY_URL%/}/org/aksw/data/faostat/faostat-qcl-2025-duckdb/${FAOSTAT_VERSION}/faostat-qcl-2025-duckdb-${FAOSTAT_VERSION}.duckdb.zst"; \
    curl -fL --retry 3 --connect-timeout 30 -o /artifacts/faostat.duckdb.zst "$url"; \
    curl -fL --retry 3 --connect-timeout 30 -o /artifacts/faostat.duckdb.zst.sha1 "$url.sha1"; \
    printf '%s  %s\n' "$(cat /artifacts/faostat.duckdb.zst.sha1)" /artifacts/faostat.duckdb.zst | sha1sum -c -; \
    zstd --decompress /artifacts/faostat.duckdb.zst -o /artifacts/faostat.duckdb; \
    test -s /artifacts/faostat.duckdb; \
    rm /artifacts/faostat.duckdb.zst; \
    chmod 0444 /artifacts/faostat.duckdb /artifacts/faostat.duckdb.zst.sha1

FROM download-tools AS jdbc
ARG DUCKDB_JDBC_VERSION
RUN set -eu; \
    mkdir -p /artifacts; \
    url="https://repo.maven.apache.org/maven2/org/duckdb/duckdb_jdbc/${DUCKDB_JDBC_VERSION}/duckdb_jdbc-${DUCKDB_JDBC_VERSION}.jar"; \
    curl -fL --retry 3 --connect-timeout 30 -o /artifacts/duckdb_jdbc.jar "$url"; \
    curl -fL --retry 3 --connect-timeout 30 -o /artifacts/duckdb_jdbc.jar.sha1 "$url.sha1"; \
    printf '%s  %s\n' "$(cat /artifacts/duckdb_jdbc.jar.sha1)" /artifacts/duckdb_jdbc.jar | sha1sum -c -; \
    chmod 0444 /artifacts/duckdb_jdbc.jar /artifacts/duckdb_jdbc.jar.sha1

# Stable data layer first, before driver or endpoint-specific configuration.
# This target can also be built/tagged for downstream FROM-based customization.
FROM ontop/ontop:5.5.0 AS data-base
COPY --from=database --chown=ontop:ontop /artifacts/faostat.duckdb /data/faostat.duckdb
COPY --from=database --chown=ontop:ontop /artifacts/faostat.duckdb.zst.sha1 /opt/ontop/input/

FROM data-base AS endpoint-base
COPY --from=jdbc --chown=ontop:ontop /artifacts/duckdb_jdbc.jar /opt/ontop/jdbc/duckdb_jdbc.jar
COPY --from=jdbc --chown=ontop:ontop /artifacts/duckdb_jdbc.jar.sha1 /opt/ontop/input/

# Small endpoint-specific layers follow all shared data/runtime layers.
FROM endpoint-base AS endpoint
ARG ENDPOINT_VERSION

COPY --chown=ontop:ontop ontop/faostat.r2rml.ttl ontop/faostat.properties ontop/faostat-constraints.lst ontop/faostat-lenses.json /opt/ontop/input/
COPY --chown=ontop:ontop README.md ontop/faostat-geographic-definitions.meta.md /opt/ontop/input/

ENV ONTOP_MAPPING_FILE=/opt/ontop/input/faostat.r2rml.ttl \
    ONTOP_PROPERTIES_FILE=/opt/ontop/input/faostat.properties \
    ONTOP_CONSTRAINT_FILE=/opt/ontop/input/faostat-constraints.lst \
    ONTOP_LENSES_FILE=/opt/ontop/input/faostat-lenses.json \
    ONTOP_LOG_LEVEL=debug
# Inherit Ontop's unprivileged user, entrypoint, port and healthcheck.

ARG FAOSTAT_VERSION
ARG DUCKDB_JDBC_VERSION
LABEL org.opencontainers.image.title="PROVIDER FAOSTAT SPARQL endpoint" \
      org.opencontainers.image.source="https://github.com/PROVIDER-Project/sparql-faostat-ontop" \
      org.opencontainers.image.description="Ontop endpoint with a preloaded FAOSTAT QCL 2025 database" \
      org.opencontainers.image.version="${ENDPOINT_VERSION}" \
      org.aksw.faostat.artifact.version="${FAOSTAT_VERSION}" \
      org.aksw.faostat.artifact.checksum.algorithm="SHA-1" \
      org.aksw.faostat.data.license="https://creativecommons.org/licenses/by/4.0/" \
      org.aksw.faostat.data.terms="https://www.fao.org/contact-us/terms/db-terms-of-use/en/" \
      org.aksw.faostat.jdbc.version="${DUCKDB_JDBC_VERSION}"
