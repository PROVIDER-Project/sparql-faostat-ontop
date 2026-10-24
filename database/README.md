# FAOSTAT preloaded database

This folder owns database generation and Maven publication. It uses the existing
DuckDB loader and separate zstd compressor containers, exporting only the archive.
There is no Makefile and no dependency on the endpoint build.

Run commands below from this folder. Maven 3.9.11+ / JDK 17+ and Docker are
recommended. Legacy runtime folders are not used or modified by a normal Maven generation. Maven output is local to this folder's `target/`.

## Build a preloaded database with Maven

`pom.xml` builds the database artifact from the pinned source CSVs, including geographic
links, audit tables, code lists and lookup indexes, then compresses it with zstd
in a separate Docker Maven Plugin execution. The
[reference generator POM](https://gitlab.com/coypu-project/data-sources/-/blob/main/disasters-with-archive/generator/pom.xml?ref_type=heads)
provides the build/run/copy/attach pattern. The POM inherits the shared AKSW
data-deployment parent. Public source downloads need no credentials.

Requirements: Maven 3.6.3+ on JDK 8+ and access to a Docker daemon (API 1.44+ by
default). Host-side DuckDB and zstd installations are unnecessary for the build.
Run from this repository:

```bash
mvn clean package
```

The published output is `target/faostat.duckdb.zst`, attached with type
`duckdb.zst` and no classifier. The uncompressed database stays on a temporary
Docker volume; only the smaller, verified archive is copied to the Maven host.
No endpoint is started and existing runtime databases are not changed.
The build uses no host bind mounts, so the Docker daemon can be remote.

The default `generate-data` profile runs these steps:

1. At `generate-resources`, `maven-dependency-plugin:copy` resolves pinned QCL
   2025 and geographic definition artifacts into `target/inputs/`: three
   compressed CSV files, geographic provenance JSON and the source README.
   Maven caches the immutable release inputs in its local repository.
2. At `process-resources`, `generate-preloaded-database` builds and runs a
   generator based on `aksw/duckdb-shell:1.5.6`, using the existing SQL and
   loader. It writes `faostat.duckdb` into an anonymous Docker volume at
   `/output`, and Maven waits for successful DuckDB commit and process exit.
3. At `prepare-package`, `compress-preloaded-database` builds and runs a
   separate compressor image. It installs Debian's zstd package on
   `debian:bookworm-slim`; no changes to `duckdb-shell` are required. The
   compressor imports the completed generator's volume by container ID,
   compresses to a `.part` file with a content checksum, runs `zstd --test`,
   and renames the checked archive to `faostat.duckdb.zst`. Compression and
   integrity-check failures fail Maven before output extraction/attachment.
4. `docker:copy` extracts only the archive. A cleanup execution stops/removes
   both containers and removes their anonymous output volume. Generator and
   compressor images remain cached; neither image contains a preloaded database.
5. At `package`, `build-helper-maven-plugin:attach-artifact` attaches the
   compressed file for Maven installation or deployment.

Each normal generation uses fresh containers and the current SQL. An old
runtime completion marker cannot skip Maven generation. `mvn clean` removes
this folder's `target/`, including staged inputs and the archive, while
preserving Maven's local cache.

The published release coordinates are:

```text
org.aksw.data.faostat:faostat-qcl-2025-duckdb:duckdb.zst:0.0.1
```

To install an already generated archive without running Docker again:

```bash
mvn -DskipGenerateData=true install
```

Do not combine this with `clean`: it requires the existing
`target/faostat.duckdb.zst`. Publication inherits the parent POM deployment
defaults; configure the intended repository and credentials for your release.
The build does not push its internal images.

Consumers must decompress before opening DuckDB or starting Ontop. For a local
copy (requires the zstd CLI and space for the expanded database):

```bash
zstd --test target/faostat.duckdb.zst
zstd --decompress --keep target/faostat.duckdb.zst
```

This produces `target/faostat.duckdb` and retains the archive. The endpoint
Dockerfile downloads and decompresses the published artifact during its build.

Settings can be overridden with Maven properties, for example:

```bash
mvn clean package -Dzstd.level=3 -Dzstd.threads=2
mvn clean package -Dgenerator.timeout=3600000 -Dcompressor.timeout=900000
mvn clean package -Ddata.repository.url=https://example.org/maven/releases
```

The default compression level is 6 with two worker threads. Timeouts are in
milliseconds: 30 minutes for generation and 10 minutes for compression. The
`duckdb.image`, `compressor.base.image`, `generator.image` and `compressor.image`
properties control the images independently. Keep DuckDB aligned with JDBC when
upgrading. SQL expects the current pinned input schemas. Override
`data.repository.url` with a repository serving the same artifact coordinates
when the mirror migrates; Compose's environment variable is independent.

If a build fails or is interrupted, run `mvn docker:stop` to remove any remaining
generator/compressor containers and their anonymous volumes before retrying.
Completed archives in `target/` are removed by `mvn clean`.

Plugin releases were checked on 22 October 2026 against Maven Central metadata:
Docker Maven Plugin **0.49.0**, Dependency **3.11.0**, Build Helper **3.6.2**,
Clean **3.5.0**, Install **3.2.0**, and Deploy **3.2.0**. Core plugins use stable
Maven 3 releases. See the [Docker Maven Plugin manual](https://dmp.fabric8.io/)
and [Build Helper attach-artifact documentation](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html).

Validated on 22 October 2026: the two-execution Maven build and subsequent
`mvn -DskipGenerateData=true install` succeeded. With zstd level 6 and two
workers, the 900,214,784-byte database became a 125,515,511-byte archive
(858.51 MiB → 119.70 MiB). Archive integrity testing and decompression passed;
the decompressed database retained 4,209,110 source rows, 4,114,755 observations,
1,222 geographic links and the original zero-valued sample. Both build
containers and their shared volume were removed. All 15 Python/SQL/compression
tests passed. The deployed endpoint and database were not changed.


## Publish a release

Change this POM's version for each new immutable database release. Configure
Maven credentials using the server ID matching the deployment destination:

```sh
mvn deploy \
  -DaltDeploymentRepository=aksw-data-releases::https://maven.inf-ai.duckdns.org/releases
```

Already published 0.0.1 must not be overwritten with regenerated bytes. For an
existing generated archive, `mvn -DskipGenerateData=true install` or `deploy`
attaches the existing `target/faostat.duckdb.zst` without regeneration; do not
combine that mode with `clean`.

The endpoint independently downloads a published release. Set its
`DATABASE_VERSION` only when adopting a new artifact; publishing this database
never rebuilds or redeploys the service.

## Tests

```sh
python3 -m unittest discover -s tests -v
sh tests/test_duckdb_shell.sh
```

Resolve the SQL fixture tests' JDBC driver through Maven (this direct plugin
goal does not run database generation):

```sh
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy \
  -Dartifact=org.duckdb:duckdb_jdbc:1.5.6.0 \
  -DoutputDirectory=target/test-dependencies
python3 -m unittest discover -s tests -v
```

SQL fixture tests use `target/test-dependencies/duckdb_jdbc-1.5.6.0.jar` by default;
set `DUCKDB_JDBC_JAR` for another location. They require a JDK. Compression
checks require host zstd. The shell smoke test needs Docker. No test depends on
legacy runtime folders or the archive under `trash/`.

## Archived workflows

The superseded source-loading Compose file is under
`../trash/database/docker-compose.source.yaml`; the two-module Maven experiment
is under `../trash/maven/`. These are reference material, not active build paths.
Their old relative paths need adjustment before reuse.

## Source and attribution

The configured input is:

https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/Production_Crops_Livestock_E_All_Data_Normalized-2025/1/Production_Crops_Livestock_E_All_Data_Normalized-2025-1-Production_Crops_Livestock_E_All_Data_Normalized.csv.zst

JDBC driver:
https://repo.maven.apache.org/maven2/org/duckdb/duckdb_jdbc/1.5.6.0/duckdb_jdbc-1.5.6.0.jar

FAO. 2025. FAOSTAT: Production: Crops and livestock products.
[Accessed on 10 October 2026]. https://www.fao.org/faostat/en/#data/QCL.
Licence: CC-BY-4.0.

Data use is subject to [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
and the [FAO Statistical Database Terms of Use](https://www.fao.org/contact-us/terms/db-terms-of-use/en/).
FAO does not endorse this service. The dataset's attribution and license are
also exposed as RDF metadata.
