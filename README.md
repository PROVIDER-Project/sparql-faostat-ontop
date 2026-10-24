# FAOSTAT over SPARQL (Ontop)

Serve the FAOSTAT Production: Crops and livestock products (QCL) 2025 snapshot
as a virtual QB/SDMX data cube. Ontop rewrites SPARQL into SQL over DuckDB;
RDF is not materialized.

The two release steps are independent:

- [`database/`](database/README.md): Maven generates and publishes a versioned
  `.duckdb.zst` artifact from pinned source data.
- [`endpoint/`](endpoint/README.md): a temporary Maven container resolves a database
  (local or remote) before Docker packaging and packages it with JDBC and mappings. Its
  Makefile provides local build/test and GHCR publishing commands.

## Build and publish the database

```sh
cd database
mvn package
# Set a new release version before publishing; configure credentials in Maven settings.
mvn deploy -DaltDeploymentRepository=aksw-data-releases::https://maven.inf-ai.duckdns.org/releases
```

Existing release coordinates:
`org.aksw.data.faostat:faostat-qcl-2025-duckdb:duckdb.zst:0.0.1`.
The output is `database/target/faostat.duckdb.zst`. Publishing an endpoint does
not generate or publish a database. Keep published release versions immutable.

## Build or publish the endpoint

From the repository root:

```sh
make -C endpoint help
make -C endpoint build
make -C endpoint up
# Once authenticated, explicitly publish the image:
make -C endpoint login GHCR_USER=YOUR_GITHUB_USERNAME
make -C endpoint publish
```

The service is available at `http://localhost:8081/sparql`. The image contains
the unpacked database and starts without data downloads, bind mounts or loading.
Images built locally use a registry-qualified name; that does not publish them.

Set endpoint and database versions independently:

```sh
make -C endpoint build VERSION=0.0.2 DATABASE_VERSION=0.0.1
```

A database can be installed into the selected host Maven repository or published
remotely before building an endpoint. `M2_DIR` defaults to `endpoint/.cache/maven` and can be
overridden through the environment, `endpoint/.env` or Make's command line.
The host's settings and optional settings-security files are mounted read-only
into the temporary resolver; they default independently to `$HOME/.m2`.
Mappings/configuration come from this Git checkout and are baked into the image.
No ad-hoc archive fallback or implicit data generation is used.

## Repository layout

```text
database/pom.xml          Database generation, compression and Maven publication
database/load.sql         Tables, code lists, lookup columns, indexes and geography
database/loader/          Load completion guard and atomic zstd compression
database/tests/           Loader, SQL and compression checks
endpoint/Dockerfile       Maven-resolved data/JDBC inputs; data layers first
endpoint/ontop/           Mappings, properties, lenses, constraints and attribution
endpoint/Makefile         Self-documenting build, test and GHCR convenience targets
endpoint/docker-compose.yaml   Local service lifecycle
endpoint/tests/           Real endpoint integration checks
```

Superseded caches, the two-module Maven experiment and the source-loading
Compose workflow are archived under ignored `trash/`. The active database
build writes to `database/target/`; the endpoint stages inputs in `endpoint/target/artifacts/` and keeps its Maven
repository in `endpoint/.cache/maven/repository/`. Docker layers use Docker storage.
Legacy runtime folders are archived under `trash/` as well. Neither active
component depends on them. SQL fixture tests resolve their own JDBC jar into
`database/target/test-dependencies/` through Maven; see the database README.
The separately maintained Helm chart is in the sibling `helm-charts`
repository. Select the published endpoint image using chart values; the chart
needs no database build logic. [Chart documentation](../helm-charts/charts/ontop/README.md).

## Tests

```sh
python3 -m unittest discover -s database/tests -v
make -C endpoint test
```

The database SQL fixture checks need a JDK and JDBC jar (`DUCKDB_JDBC_JAR`);
loader/compression checks need Python and, for compression, zstd. Endpoint
checks build the selected image and query an isolated container with no network
or host mounts. Historical setup and validation notes are archived locally
under `trash/docs/`.

## Layout validation (24 October 2026)

The relocated Maven database build and all 15 database checks passed in the
previous layout validation. The current endpoint workflow passed seven Makefile
orchestration checks and five real SPARQL/image checks. Its image was built with
Maven offline from the project-local cache, including read-only settings/security
mounts and an explicit cache override of settings.xml's localRepository. The
cache was seeded with previously downloaded artifacts; the database matched the
published checksum. Compose configuration also validated. No image was published
and no deployed service was restarted. Superseded workflows remain in `trash/`.

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
QCL 2025 observations. The [source and policy record](endpoint/ontop/faostat-geographic-definitions.meta.md)
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
