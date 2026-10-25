# FAOSTAT over SPARQL

Serve the FAOSTAT QCL 2025 snapshot as a virtual QB/SDMX data cube using Ontop
and DuckDB. The [database build](database/README.md) publishes a compressed Maven
artifact; the [endpoint build](endpoint/README.md) packages it with the mappings.

## Build and run

Requires Maven, a JDK, GNU Make and Docker with BuildKit/Compose.
From the repository root:

```sh
mvn -f database/pom.xml -P local deploy
make -C endpoint up
```

The `local` profile publishes the generated dataset to `database/target/m2`
and skips installation into your normal Maven repository. Without this profile,
`mvn install` and `mvn deploy` also put the dataset alongside your other Maven
artifacts (usually in `~/.m2/repository`). Source and plugin dependencies still
use Maven's configured cache in either case.

The endpoint uses `database/target/m2` by default when present, with its own
Maven cache and remote repositories available too. Override the publication
folder with `DATABASE_REPOSITORY` or disable it with `DATABASE_REPOSITORY=`:

```sh
make -C endpoint build DATABASE_REPOSITORY=/path/to/m2
```

Settings can also go in `endpoint/.env`; see
[endpoint configuration](endpoint/README.md#configuration).
The service is available at [localhost:8081/sparql](http://localhost:8081/sparql).
Use `make -C endpoint down` to stop it and `make -C endpoint help` for all targets.

## Publish

Database and endpoint releases have independent versions. Choose a new database
version in `database/pom.xml` before publishing a new immutable release:

```sh
mvn -f database/pom.xml deploy \
  -DaltDeploymentRepository=aksw-data-releases::https://maven.inf-ai.duckdns.org/releases
make -C endpoint login GHCR_USER=YOUR_GITHUB_USERNAME
make -C endpoint publish VERSION=0.0.2 DATABASE_VERSION=0.0.1
```

The current database coordinates are
`org.aksw.data.faostat:faostat-qcl-2025-duckdb:duckdb.zst:0.0.1`.
Maven publication uses credentials from `settings.xml`; GHCR uses Docker login.
Building an endpoint locally does not publish it.

## Design

- `database/`: SQL, loader scripts, Maven generation and publication. Inputs and
  scripts are bind mounted into build containers; datasets stay out of image
  build archives. Completion markers skip repeated loading and compression.
- `endpoint/`: Maven artifact resolution, Docker packaging, mappings and a
  convenience Makefile. The image contains the unpacked read-only database and
  needs no runtime data download. Data layers precede JDBC and configuration.
- The sibling [Helm chart](../helm-charts/charts/ontop/README.md) deploys the
  selected endpoint image independently of the database build.

After changing database inputs or loading settings, rebuild with
`mvn -f database/pom.xml -P local clean deploy`. This also removes the local
publication repository. Use new release versions when changing published data;
Maven may reuse an already cached release.

## Data model

The namespace is `https://example.org/faostat/`; the dataset is
`dataset/QCL` with identifier `QCL-2025`. Observation IRIs use
`observation/QCL/{area}-{item}-{element}-{year}`, for example
`observation/QCL/2-221-5312-1961`. Negative signs are escaped as `~2D`.
Only rows with non-null values and complete keys become observations; zero
values are included. RDF is generated virtually, rather than materialized.

| Dimension / attribute | Predicate |
| --- | --- |
| Area | `sdmx-dimension:refArea` |
| Item | `ex:item` |
| Element | `ex:element` |
| Year | `sdmx-dimension:refPeriod` (`xsd:gYear`) |
| Value | `sdmx-measure:obsValue` (`xsd:double`) |
| Unit | `sdmx-attribute:unitMeasure` |
| Flag / note | `ex:flag` / `ex:note` |

Code lists are SKOS schemes, deduplicated during loading into keyed tables.
Areas expose `ex:m49Code` and items `ex:cpcCode` as strings, retaining leading
zeros. Missing flags and notes produce no RDF term.

Areas link through `ex:hasCountry` to shared
`https://example.org/country/{ISO3}` IRIs. Definitions retrieved on 15 October
2026 describe country/group membership, not membership in each observation year.
These links do not allocate regional values to countries: summing values across
a membership join can overcount. Historical and non-country exclusions, China
handling and audit tables are documented in the
[geographic policy record](endpoint/ontop/faostat-geographic-definitions.meta.md).

## Example query

```sparql
PREFIX ex: <https://example.org/faostat/vocab/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?area ?label WHERE {
  ?area ex:hasCountry <https://example.org/country/CAN> ;
        skos:prefLabel ?label .
}
```

This returns Canada's own area and source-listed groups containing Canada.

## Tests

See the [database tests](database/README.md#tests) for SQL fixtures and script
checks. Run `make -C endpoint check` for orchestration checks or
`make -C endpoint test` to build and query an isolated endpoint container.

## Sources and licence

FAO. 2025. [FAOSTAT: Production: Crops and livestock products](https://www.fao.org/faostat/en/#data/QCL).
Accessed 10 October 2026; geographic definitions accessed 15 October 2026.
The transformed data artifact is distributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to the
[FAO Statistical Database Terms of Use](https://www.fao.org/contact-us/terms/db-terms-of-use/en/).
Retain attribution and identify transformations. FAO does not endorse this
service. Software and external components retain their respective licences.
