# FAOSTAT over SPARQL (Ontop)

Serve the FAOSTAT **Production: Crops and livestock products** (QCL) 2025
snapshot as a virtual QB/SDMX data cube. Ontop rewrites SPARQL into SQL
against DuckDB; RDF is not materialized.

This mirrors `../sparql-tiva-ontop`: the same three Compose services and pinned
images (curl 8.10.1, `aksw/duckdb-shell:1.5.6`, Ontop 5.5.0), DuckDB JDBC
1.5.6.0, R2RML, read-only JDBC, query logging, keyed observation lenses,
precomputed code lists, lookup indexes and a guarded transactional loader.

## Start

Requires Docker and Docker Compose with dependency completion conditions.
Allow several GB of disk space for data, JDBC, the indexed database and temporary
rebuild space, plus container images. The indexed snapshot tested below occupied
about 856 MiB, compared with about 51 MiB before these changes.

```bash
docker compose up -d
```

1. `fetch` downloads the deployed QCL CSV.zst, geographic definition CSV.zst
   files, their source provenance/README, and JDBC driver. Existing nonempty
   files are reused. New downloads go to `.part` files and are renamed only
   after curl succeeds, preventing interrupted downloads from becoming cached inputs.
2. `load` skips opening DuckDB when both `./run/faostat.duckdb.complete` and a
   nonempty database exist. Otherwise `ontop/load.sql` rebuilds `faostat`, five
   small code-list tables, geographic definitions/country links and audit tables,
   derived lookup columns and indexes in one transaction,
   runs `ANALYZE`, and commits. The loader creates the completion marker only
   after DuckDB exits successfully. All CSV fields are read as strings before
   explicit conversion; M49 and CPC codes keep their leading zeros. The leading
   apostrophe FAOSTAT uses to protect these codes in spreadsheets is removed
   from those two database fields. Source CSV bytes remain unchanged.
3. `ontop` loads the mapping, constraints and observation lens, opens that
   database read-only and serves
   `http://localhost:8081/sparql`. Port 8081 allows TiVA to use 8080 alongside it.

Override the host port with `ONTOP_PORT=8091 docker compose up -d`.
The completion marker survives `docker compose down` / `up` with the database.
A failed load leaves no marker and prevents Ontop from starting. A stale marker
with a missing or empty database triggers loading again. The marker is manual:
changes to source data, SQL or mapping do not automatically invalidate it.
An old database with no marker is rebuilt once on adopting this setup.

The new mapping requires the new schema, so rebuild once before using it.
Stop Ontop before reloading, because DuckDB permits one writer or multiple
read-only processes, not a concurrent writer and readers:

```bash
docker compose stop ontop
rm -f ./run/faostat.duckdb.complete
docker compose run --rm load && docker compose up -d --no-deps --force-recreate ontop
```

To refresh cached inputs, stop the stack (`docker compose down`), remove the
corresponding file in `data/` or `jdbc/`, then start again. When changing the
source dataset, also remove `run/faostat.duckdb.complete` to request a rebuild.
Runtime directories
are ignored by Git. Do not edit the deployed release in place; use another
artifact URL for another snapshot.

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

**Upgrade:** stop Ontop, remove `run/faostat.duckdb.complete`, and rebuild using
the reload commands above. The completion marker is manual; old databases do
not automatically acquire these tables. `docker compose run --rm load` also
runs the fetch dependency to obtain any missing definition files.

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

- `docker-compose.yaml`: fetch, load and endpoint services.
- `ontop/faostat.r2rml.ttl`: observations, code lists and cube metadata.
- `ontop/faostat.properties`: read-only JDBC, query logging and strict cardinality.
- `ontop/faostat-constraints.lst`: fact composite key and code-list keys.
- `ontop/faostat-lenses.json`: observation filter, composite/local-name keys and non-null declarations.
- `ontop/load.sql`: transactional load, code lists, derived columns, indexes and statistics.
- `loader/load-duckdb.sh`: completion marker, skip and retry behavior.
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

```bash
python3 -m unittest discover -s tests -v
sh tests/test_duckdb_shell.sh
```

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
