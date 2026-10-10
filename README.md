# FAOSTAT over SPARQL (Ontop)

Serve the FAOSTAT **Production: Crops and livestock products** (QCL) 2025
snapshot as a virtual QB/SDMX data cube. Ontop rewrites SPARQL into SQL
against DuckDB; RDF is not materialized.

This mirrors `../sparql-tiva-ontop`: the same three Compose services and pinned
images (curl 8.10.1, DuckDB 1.5.6, Ontop 5.5.0), DuckDB JDBC 1.5.6.0, R2RML,
read-only JDBC and query logging.

## Start

Requires Docker and Docker Compose with dependency completion conditions.
Allow about 1 GB of disk space for data, JDBC and the database, plus container images.

```bash
docker compose up -d
```

1. `fetch` downloads the deployed CSV.zst and JDBC driver. Existing nonempty
   files are reused. New downloads go to `.part` files and are renamed only
   after curl succeeds, preventing interrupted downloads from becoming cached inputs.
2. `load` creates `./run/faostat.duckdb`, replaces table `faostat`, and imports
   `./data/FAOSTAT.csv.zst` directly. All CSV fields are read as strings before
   explicit conversion; M49 and CPC codes keep their leading zeros. The leading
   apostrophe FAOSTAT uses to protect these codes in spreadsheets is removed
   from those two database fields. Source CSV bytes remain unchanged.
3. `ontop` opens that database read-only and serves
   `http://localhost:8081/sparql`. Port 8081 allows TiVA to use 8080 alongside it.

Override the host port with `ONTOP_PORT=8091 docker compose up -d`.
The database rebuild follows TiVA's behavior when the load service runs.
Stop Ontop before manually reloading, because DuckDB permits one writer or
multiple read-only processes, not a concurrent writer and readers:

```bash
docker compose stop ontop
docker compose run --rm load
docker compose up -d ontop
```

To refresh cached inputs, stop the stack (`docker compose down`), remove the
corresponding file in `data/` or `jdbc/`, then start again. Runtime directories
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
`observation/QCL/{AREA_CODE}/{ITEM_CODE}/{ELEMENT_CODE}/{YEAR}`.
Only rows with non-null values are exposed as observations. Zero values are included.
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

Area, item, element, unit and flag code lists are SKOS concept schemes derived
from distinct values in the main data. Area, item and element labels come from
the CSV; units use their literal text as labels. Flags expose notation only:
the separate flags lookup artifact is not loaded. Areas carry `ex:m49Code`
and items carry `ex:cpcCode` as strings. Areas may include aggregates and are
not automatically equated with countries. The source's `YEAR_CODE` is retained
in DuckDB; `YEAR` defines the RDF time dimension.

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
- `ontop/faostat.properties`: read-only JDBC and query logging.
- `ontop/faostat-constraints.lst`: composite key `(AREA_CODE, ITEM_CODE, ELEMENT_CODE, YEAR)`.

The declared key must remain unique for any replacement dataset. Consolidating
the vocabulary namespace and adding explicit links from area concepts to external
geographies remain open work, as in TiVA. All column-based literals use explicit
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

The generated DuckDB file is approximately 51 MB for this snapshot.
