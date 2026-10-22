# FAOSTAT over SPARQL (Ontop)

Serve the FAOSTAT **Production: Crops and livestock products** (QCL) 2025
snapshot as a virtual QB/SDMX data cube. Ontop rewrites SPARQL into SQL
against DuckDB; RDF is not materialized.

The default Docker image includes published preloaded database release **0.0.1**,
DuckDB JDBC 1.5.6.0, matching mappings/lenses/constraints and source attribution.
Database download, checksum verification and decompression happen during the
image build. Starting the endpoint needs no data downloads or ingestion.

## Start the release endpoint

Requires Docker and Docker Compose with image-build support. Allow space for the
uncompressed database (about 859 MiB), JDBC/runtime and build cache. Although the
published database is about 120 MiB compressed, the final image stores the
expanded DuckDB file.

```bash
docker compose up -d --build --remove-orphans
```

The single `ontop` service serves `http://localhost:8081/sparql`. Override the host
port with `ONTOP_PORT=8091 docker compose up -d --build --remove-orphans`.
`--remove-orphans` removes the former stopped `fetch`/`load` service containers
when switching an existing checkout. Files in `data/`, `jdbc/` and `run/` are
retained, but the default endpoint uses the database and configuration baked
into its image. It has no host bind mounts.

`Dockerfile` builds two stages:

1. A disposable Debian stage downloads the published database and the pinned
   JDBC driver with their `.sha1` sidecars, verifies both SHA-1 checksums,
   and decompresses the database.
   Download failures, checksum mismatches or corrupt archives fail the build.
2. The final stage uses `ontop/ontop:5.5.0`, with the verified database, JDBC jar,
   matching R2RML/properties/constraints/lens files and attribution documents.
   Download tools and the compressed archive stay out of the final image.

The database file has mode `0444`; Ontop runs as its inherited non-root user and
connects through read-only JDBC. The image inherits Ontop's healthcheck. Baked
`ONTOP_*` defaults also support ordinary `docker run` use. Compose retains the
configurable log level (`ONTOP_LOG_LEVEL`, default `debug`). Image labels record
the database version, checksum algorithm and JDBC version. The downloaded
`.sha1` sidecars are retained under `/opt/ontop/input/` for traceability.

The build context is an explicit `.dockerignore` allowlist. Cached source data,
local databases, JDBC downloads, Maven outputs and Git metadata are excluded.
Changing mappings or properties requires rebuilding the endpoint image.

The Dockerfile puts the database in the first added runtime layer (`data-base`),
then adds JDBC (`endpoint-base`), followed by mappings, configuration, attribution
and endpoint labels (`endpoint`). Database and driver downloads use independent
build stages. Mapping-only variants reuse the shared data/runtime layers when
built from the same base and artifact inputs. Changing a driver does not invalidate
the database download or its runtime layer.

For exact reuse across downstream repositories, publish the `endpoint-base`
target once and derive customized images from that image, ideally pinned by digest:

```bash
docker build --target endpoint-base -t provider/faostat-ontop-base:0.0.1 .
```

This target contains Ontop, the database, JDBC and checksum sidecars; a derived
image must add mappings/properties/lenses/constraints and set the corresponding
`ONTOP_*_FILE` variables. It is a customization base, not a ready endpoint.
Alternatively, `data-base` contains Ontop plus just the database and its checksum.
Layer sharing assumes identical base-image and filesystem-layer contents; independently
recreating downloads on another builder is not a guarantee of identical layer digests.

### Published input and upgrades

Database release:

[faostat-qcl-2025-duckdb-0.0.1.duckdb.zst](https://maven.inf-ai.duckdns.org/releases/org/aksw/data/faostat/faostat-qcl-2025-duckdb/0.0.1/faostat-qcl-2025-duckdb-0.0.1.duckdb.zst)

The build obtains checksums by appending `.sha1` to each Maven download URL.
The database checksum is provided by
[its Maven sidecar](https://maven.inf-ai.duckdns.org/releases/org/aksw/data/faostat/faostat-qcl-2025-duckdb/0.0.1/faostat-qcl-2025-duckdb-0.0.1.duckdb.zst.sha1);
the JDBC download uses the same convention. Neither checksum is hard-coded.
Artifact and checksum download failures or mismatches fail the build.

For a new release, update the database version and use its matching mapping files.
Defaults are pinned to the release above; no changing
`SNAPSHOT` or latest-version resolution occurs. The repository URL is separately
overridable with `--build-arg FAOSTAT_REPOSITORY_URL=...` if the mirror migrates.
An explicit override build could use:

```bash
FAOSTAT_IMAGE=provider/sparql-faostat-ontop:0.0.2 docker compose build \
  --build-arg FAOSTAT_VERSION=0.0.2
FAOSTAT_IMAGE=provider/sparql-faostat-ontop:0.0.2 \
  docker compose up -d --no-build --remove-orphans
```

Changing either `FAOSTAT_VERSION` or `DUCKDB_JDBC_VERSION` selects the artifact
and its matching Maven checksum automatically. Keep JDBC compatible with the
database's DuckDB version. The Dockerfile currently constructs standard Maven
repository URLs; a future Maven Resolver/CLI integration can resolve coordinates
if repository layout or resolution requirements change. Publish each data
revision under a new immutable Maven release version and endpoint image tag.

### Endpoint image validation (22 October 2026)

The release image built successfully from the published artifact and passed all
20 loader/SQL/compression/endpoint tests. The endpoint started with networking
disabled and no host bind mounts, returning 4,114,755 observations and 1,222
country links. Fixed-subject values and literal datatypes, leading-zero codes,
and read-only database permissions passed. Downloaded Maven `.sha1` sidecars
are verified before decompression. The existing deployed endpoint was not
replaced during these isolated checks.

## Kubernetes with Helm

The shared chart in the sibling `helm-charts/charts/ontop` directory
deploys the baked endpoint as a Deployment and Service, with
optional Ingress, startup/readiness/liveness probes and resource settings.
Each replica serves its own read-only image snapshot. There are no PVCs or
runtime download/ingestion Jobs. The chart supplies writable ephemeral `/tmp`
storage for JDBC native libraries and DuckDB query spill files.

```bash
docker compose build
# Publish the image to a cluster-accessible registry or load it into local nodes.
helm upgrade --install faostat ../helm-charts/charts/ontop \
  -f ../helm-charts/examples/faostat.yaml \
  --namespace provider --create-namespace --wait --timeout 5m
helm test faostat --namespace provider --logs
```

The FAOSTAT example selects `provider/sparql-faostat-ontop:0.0.1`; registry and
digest overrides, local Kind loading, Ingress/TLS examples and runtime settings
are documented in [the shared chart README](../helm-charts/charts/ontop/README.md).

The chart was validated in a temporary Kind cluster: installation, Helm test,
Service queries, scaling to two replicas and rollback passed. Ingress/TLS
manifests passed API-server dry-run validation. Chart rendering tests now live
in the sibling `helm-charts` repository.

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
No endpoint is started and the existing `run/faostat.duckdb` is not changed.
The build uses no host bind mounts, so the Docker daemon can be remote.

The default `generate-data` profile runs these steps:

1. At `generate-resources`, `maven-dependency-plugin:copy` resolves pinned QCL
   2025 and geographic definition artifacts into `target/inputs/`: three
   compressed CSV files, geographic provenance JSON and the source README.
   Maven caches the immutable release inputs in its local repository; the
   existing Compose `data/` cache is independent.
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

Each normal generation uses fresh containers and the current SQL. Compose's
completion-marker guard still applies to Compose runs; an old `run/` marker
cannot skip Maven generation. `mvn clean` removes `target/`, including staged
inputs and the archive, while preserving Compose data and Maven's local cache.

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

## Development: load directly from source

`docker-compose.source.yaml` preserves the original `fetch` → `load` → `ontop`
workflow for source/mapping development. Select it explicitly:

```bash
docker compose -f docker-compose.source.yaml up -d
```

It downloads cached QCL/geographic CSVs and JDBC into `data/` and `jdbc/`, builds
`run/faostat.duckdb` with `ontop/load.sql`, and mounts that database and the
local mapping files into Ontop. Downloads use `.part` files and rename only
on success. The loader skips opening DuckDB when a nonempty database and its
`.complete` marker already exist. Failed loads leave no marker; stale markers
with a missing/empty database trigger loading again. The marker is manual:
source, SQL and mapping changes do not automatically invalidate it.

Stop any endpoint using `run/faostat.duckdb` before rebuilding it:

```bash
docker compose -f docker-compose.source.yaml stop ontop
rm -f ./run/faostat.duckdb.complete
docker compose -f docker-compose.source.yaml run --rm load && \
  docker compose -f docker-compose.source.yaml up -d --no-deps --force-recreate ontop
```

This source workflow and the default baked-image workflow use the same default
host port. Use a separate Compose project and `ONTOP_PORT` when running both
at once. Source-workflow caches and markers do not affect the default release
image. `GEOGRAPHIC_DEFINITIONS_BASE_URL` applies to the source fetch service;
Maven and the endpoint Docker build have their own repository settings.

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

## Model

The provisional namespace is `https://example.org/faostat/`, following TiVA's
example-namespace convention. Observation IRIs are
`observation/QCL/{OBSERVATION_LOCAL_NAME}`, where the local name is the four
integer key components separated by hyphens (e.g. `2-221-5312-1961`). This changes
observation identifiers from `.../QCL/2/221/5312/1961` to
`.../QCL/2-221-5312-1961`; update any saved observation links. Negative component
signs are escaped as `~2D` to keep the encoding reversible and collision-free.
Dataset, code-list and vocabulary IRIs are unchanged.
Only rows with non-null values and complete subject keys are exposed as
observations. Zero values are included.
The dataset is `https://example.org/faostat/dataset/QCL` and has identifier
`QCL-2025`. Missing optional flags and notes produce no RDF term.

| Dimension / attribute | Predicate | Database column |
| --- | --- | --- |
| Area | `sdmx-dimension:refArea` | `AREA_CODE` |
| Item | `ex:item` | `ITEM_CODE` |
| Element | `ex:element` | `ELEMENT_CODE` |
| Year | `sdmx-dimension:refPeriod` | `YEAR`, `xsd:gYear` |
| Value | `sdmx-measure:obsValue` | `OBS_VALUE`, `xsd:double` |
| Unit | `sdmx-attribute:unitMeasure` | `UNIT` |
| Flag | `ex:flag` | `FLAG` |
| Note | `ex:note` | `NOTE`, `xsd:string` |

Area, item, element, unit and flag code lists are SKOS concept schemes deduplicated once
during loading into small tables with primary keys, including codes from rows
with null observation values. Area, item and element labels come from
the CSV; units use their literal text as labels. Flags expose notation only:
the separate flags lookup artifact is not loaded. Areas carry `ex:m49Code`
and items carry `ex:cpcCode` as strings. Areas may include aggregates and are
not automatically equated with countries. The source's `YEAR_CODE` is retained
in DuckDB; `YEAR` defines the RDF time dimension.

## Area-to-country links

The loader consumes the archived FAOSTAT geographic definitions retrieved on
15 October 2026, revision 1. These are global definitions, separate from the
QCL 2025 observations. The [source and policy record](ontop/faostat-geographic-definitions.meta.md)
contains original FAO URLs, exact artifact URLs, hashes and derivation rules.
The artifact repository is a temporary retrieval location. To migrate it,
set `GEOGRAPHIC_DEFINITIONS_BASE_URL` to the replacement directory containing
the same artifact filenames. Existing nonempty downloads are reused.

`faostat_country_definition` retains the source concordance;
`faostat_area_membership` retains every source member row. The keyed
`faostat_area_country` table exposes distinct country links as
`ex:hasCountry`, using TiVA's shared `https://example.org/country/{ISO3}` IRIs.
It adds no descriptions to those country resources. A country-code index
supports reverse lookups:

```sparql
PREFIX ex: <https://example.org/faostat/vocab/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?area ?label WHERE {
  ?area ex:hasCountry <https://example.org/country/CAN> ;
        skos:prefLabel ?label .
}
```

This includes Canada's own area and source-listed groups containing Canada.
TiVA and FAOSTAT currently have different predicate namespaces; their country
object IRIs are shared. Area concepts remain the QCL code list.

Explicitly ended historical areas and non-country identifiers are excluded.
Four additional source-code exceptions are documented in the policy record.
China's aggregate (351) receives no inferred country expansion; mainland China,
Hong Kong, Macao and Taiwan retain separate source identities. Inspect the SQL
tables `faostat_area_country_unresolved` and `faostat_area_member_exclusion`
for omissions; all original source definitions remain available.

Group memberships describe the retrieved classification, not the year of each
observation. They do not allocate aggregate values to countries; summing a
regional value repeated through a country-membership join would overcount.

**Upgrade:** published database release 0.0.1 already contains these tables.
For the baked endpoint, upgrade the artifact and image together as described
above. Source-workflow users must stop the reader, remove the completion marker
and run the source reload commands; old local databases do not acquire tables
automatically.

## Queries

Count observations:

```bash
curl --fail -s 'http://localhost:8081/sparql' \
  --data-urlencode 'query=PREFIX qb: <http://purl.org/linked-data/cube#>
    SELECT (COUNT(*) AS ?n) WHERE { ?o a qb:Observation }' \
  -H 'Accept: application/sparql-results+json'
```

Read Afghanistan's 1961 area harvested for almonds in shell:

```sparql
PREFIX ex: <https://example.org/faostat/vocab/>
PREFIX qb: <http://purl.org/linked-data/cube#>
PREFIX sdmx-dimension: <http://purl.org/linked-data/sdmx/2009/dimension#>
PREFIX sdmx-attribute: <http://purl.org/linked-data/sdmx/2009/attribute#>
PREFIX sdmx-measure: <http://purl.org/linked-data/sdmx/2009/measure#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?observation ?value ?unit ?flag WHERE {
  ?observation a qb:Observation ;
    sdmx-dimension:refArea <https://example.org/faostat/area/2> ;
    ex:item <https://example.org/faostat/item/221> ;
    ex:element <https://example.org/faostat/element/5312> ;
    sdmx-dimension:refPeriod "1961"^^xsd:gYear ;
    sdmx-measure:obsValue ?value ;
    sdmx-attribute:unitMeasure ?unit .
  OPTIONAL { ?observation ex:flag ?flag }
}
```

Look up an area's label and M49 code:

```sparql
PREFIX ex: <https://example.org/faostat/vocab/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?label ?m49 WHERE {
  <https://example.org/faostat/area/2> skos:prefLabel ?label ; ex:m49Code ?m49 .
}
```

## Files and open work

- `pom.xml`: Docker-backed generator and attached preloaded DuckDB Maven artifact.
- `../helm-charts`: shared Helm chart and rendering tests for baked endpoints.
- `Dockerfile`: verified published database/JDBC downloads and baked Ontop endpoint.
- `.dockerignore`: minimal endpoint image build context.
- `docker-compose.yaml`: single-service release endpoint.
- `docker-compose.source.yaml`: optional fetch/load/endpoint source workflow.
- `tests/test_endpoint_image.py`: opt-in offline endpoint integration checks.
- `ontop/faostat.r2rml.ttl`: observations, code lists and cube metadata.
- `ontop/faostat.properties`: read-only JDBC, query logging and strict cardinality.
- `ontop/faostat-constraints.lst`: fact composite key and code-list keys.
- `ontop/faostat-lenses.json`: observation filter, composite/local-name keys and non-null declarations.
- `ontop/load.sql`: transactional load, code lists, derived columns, indexes and statistics.
- `loader/load-duckdb.sh`: completion marker, skip and retry behavior.
- `loader/compress-duckdb.sh`: checked, atomic zstd archive creation for Maven.
- `tests/test_compression.py`: round trips and failure cleanup (requires zstd).
- `tests/test_loader.py`: loader lifecycle tests with a fake DuckDB executable.
- `tests/test_load_sql.py` and `tests/DuckDbScripts.java`: real JDBC SQL fixture checks.
- `tests/test_duckdb_shell.sh`: real image/loader smoke test.

The declared key must remain unique for any replacement dataset. Consolidating
the vocabulary namespace and resolving the explicitly audited area omissions
remain open work. All column-based literals use explicit
RDF datatypes. Debug logging records SPARQL and reformulated SQL.

## Verified snapshot

Verified on 10 October 2026 using the deployed artifact and the Compose stack:

- 4,209,110 source rows covering 1961–2024; 4,114,755 non-null-value observations.
- Composite key unique, with no missing key fields.
- SPARQL observation count and a join across all required cube fields match DuckDB.
- Sample Afghanistan/almonds/area harvested/1961 returns zero, unit `ha`, flag `A`.
- M49 `004` and CPC `01371` retain leading zeros; year, value and note datatypes checked.
- Dataset attribution/license, eight cube components and five concept schemes query correctly.
- Atomic download behavior checked for failure, success and cache reuse.
- Compose configuration valid; fetch/load completed successfully and Ontop reported healthy.

The original, unindexed DuckDB file was approximately 51 MB for this snapshot.

## Query planning and indexes

Keep `ontop.cardinalityMode=STRICT`: RDF triples must be unique and SPARQL
result multiplicities must be preserved. The `faostat_observations` BasicLens
exposes the observation composite and local-name keys to Ontop. Unique indexes
enforce the original fact key and observation local-name key in DuckDB; null
subject components are filtered out by the lens. Code-list primary keys reject
conflicting labels or secondary codes rather than picking one arbitrarily.
The R2RML sources contain no `DISTINCT`; code lists are deduplicated during load.
These keys remove the need to deduplicate those mapping sources on each query,
but do not guarantee that every possible Ontop plan omits `DISTINCT`.

Following TIVA, calculated lookup values are stored and indexed as ordinary
columns rather than indexed expressions. DuckDB supports selective ART lookup
scans on single-column indexes; composite and expression indexes are ineligible
for those scans. See [DuckDB indexing](https://duckdb.org/docs/current/guides/performance/indexing).
The loader builds nine single-column indexes after ingestion:

- `OBSERVATION_LOCAL_NAME` for fixed observation subjects;
- `AREA_CODE_LEXICAL`, `ITEM_CODE_LEXICAL`, `ELEMENT_CODE_LEXICAL` for dimension IRIs;
- `YEAR_LEXICAL` for `xsd:gYear` objects;
- `OBS_VALUE_LEXICAL` for exact `xsd:double` objects;
- `UNIT`, `FLAG` and `NOTE` for their mapped objects.

The tenth fact index is the composite unique index for integrity. Code-list
primary keys already supply their indexes. Stored lexical columns avoid
query-time casts in exact lookups. The original integer and double columns
remain available for SQL analysis; mapped year, value, notation and note RDF
datatypes are preserved. Numeric SPARQL filters and aggregates can still require
casts of the lexical value. Common objects and unbound triple queries may scan
many rows; indexes do not make whole-graph enumeration cheap.

[Ontop lenses](https://ontop-vkg.org/guide/advanced/lenses) documents the key and
non-null declarations used here. To inspect SQL without running a large query,
start a temporary Ontop development endpoint with the new mapping, constraints
and lens (adjust the JDBC path for a local CLI installation):

```bash
ontop endpoint --dev \
  -m ontop/faostat.r2rml.ttl \
  -p ontop/faostat.properties \
  -c ontop/faostat-constraints.lst \
  --lenses ontop/faostat-lenses.json

curl -fsS 'http://localhost:8080/ontop/reformulate' \
  --data-urlencode 'query=SELECT * WHERE { ?s ?p ?o } LIMIT 1000'
```

Check the reformulated SQL for unnecessary duplicate elimination and direct
stored-column equalities. Use DuckDB `EXPLAIN` to inspect plans, or profiling on
small selective queries to confirm actual index scans. Retain strict semantics;
changing to `LOOSE` can affect counts, sums and limits.

## Tests and updated snapshot validation

To test a built release image as well as the loader/SQL/compression tests:

```bash
docker compose build
FAOSTAT_ENDPOINT_IMAGE=provider/sparql-faostat-ontop:0.0.1 \
  python3 -m unittest discover -s tests -v
```

The five image tests start a temporary container with networking disabled and no
host bind mounts. They verify startup, observation and country-link counts,
fixed-subject values/datatypes, leading-zero codes, and database read-only file
permissions. The container is removed after testing. Without
`FAOSTAT_ENDPOINT_IMAGE`, these tests skip explicitly. The fixture counts target
release 0.0.1 and must be reviewed when adopting a different dataset release.


```bash
python3 -m unittest discover -s tests -v
sh tests/test_duckdb_shell.sh
```

Four compression tests use the zstd CLI (and skip explicitly if it is absent);
they check byte-for-byte round trips, replacement, invalid inputs and cleanup
after compression or integrity-check failures.

The five loader lifecycle tests need Python 3 only. Six SQL fixture tests also
need a JDK and the downloaded `jdbc/duckdb_jdbc-1.5.6.0.jar` (or set
`DUCKDB_JDBC_JAR`); they skip with an explicit reason if those are unavailable.
They check country identities/group links, historical and non-country exclusions,
ISO3 conflicts and duplicate memberships, as well as zero/null values, lexical
lookup columns, leading-zero codes,
negative-key encoding, code-list coverage, indexes, repeat rebuilds, and rollback
on duplicate fact keys or conflicting code-list labels. The shell smoke test
requires Docker access and checks the published image and actual loader.

On 11 October 2026, the new SQL was tested with DuckDB JDBC 1.5.6.0 against the
full cached source in a separate database:

- 4,209,110 rows and 4,114,755 observations, matching the original snapshot;
- 244 areas, 301 items, 14 elements, 10 units and 5 flags;
- both unique indexes built successfully;
- the Afghanistan/almonds/1961 sample retains value `0.0`, unit `ha`, flag `A`,
  M49 `004` and CPC `01371`;
- a lookup for `OBSERVATION_LOCAL_NAME='2-221-5312-1961'` used an index scan;
- all eight Python/SQL tests, Compose configuration and shell syntax passed.

The deployed database was not replaced during these checks. Docker daemon
access was unavailable, so the updated Ontop endpoint, generated SQL, numeric
SPARQL filters/aggregates and image smoke test were not revalidated in this run.
The earlier endpoint verification above describes the original mapping.

## Geographic-link validation (15 October 2026)

The revised loader was run against the full cached QCL source in a separate
database, then served through Ontop 5.5.0 with the configured mapping,
constraints and lens:

- 4,209,110 source rows and 4,114,755 observations retained.
- 374 country/region definitions and 2,551 membership rows retained.
- 249 eligible country codes; 1,222 distinct area-to-country links across
  236 of the 244 QCL areas (202 single-country areas and 34 groups).
- Eight areas remain explicitly unresolved: seven historical areas and
  China's aggregate (351).
- EU27 yields 27 eligible countries from 30 raw member rows.
- SPARQL link/observation totals match SQL; Canada's reverse lookup returns
  Canada, World, Americas and Northern America. TWN remains separate;
  historical and China-aggregate links are absent. The original zero-valued
  Afghanistan sample is unchanged.
- Decompressed downloads match the source provenance SHA-256 checksums.
- All 11 loader/SQL tests, Compose configuration, shell syntax and the real
  DuckDB image/loader smoke test passed.
