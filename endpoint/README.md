# FAOSTAT Ontop endpoint

A self-contained Ontop image built from a published FAOSTAT database artifact.
The database is downloaded, checksum-verified and decompressed during image
build. Starting a container requires no database download or ingestion.

Run `make help` in this folder for available targets. GNU Make, Docker with
BuildKit/Compose, and Python 3 for endpoint tests are required. Allow space for
the expanded database (~859 MiB), JDBC/runtime and Docker build cache.

## Build and run

```sh
make build
make test
make up
make logs
make down
```

The default image is `ghcr.io/provider-project/sparql-faostat-ontop:0.0.1`.
Building that tag locally does not publish it or assume it already exists in
GHCR. `make up` builds then starts the service at `http://localhost:8081/sparql`;
`make down` stops this Compose project. Compose's explicit project name is
`sparql-faostat-ontop`, retaining the former root Compose project's identity.
These lifecycle commands affect that project only when explicitly invoked.

## Independent versions

```sh
make build VERSION=0.0.2 DATABASE_VERSION=0.0.1
make up VERSION=0.0.2 DATABASE_VERSION=0.0.1 PORT=8091
make show-config
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `VERSION` | `0.0.1` | Endpoint image release and OCI version label |
| `DATABASE_VERSION` | `0.0.1` | Published DuckDB artifact release |
| `DUCKDB_JDBC_VERSION` | `1.5.6.0` | JDBC release, compatible with the database |
| `REPOSITORY` | `ghcr.io/provider-project/sparql-faostat-ontop` | Image repository |
| `IMAGE` | `$(REPOSITORY):$(VERSION)` | Full image reference override |
| `DATA_REPOSITORY_URL` | `https://maven.inf-ai.duckdns.org/releases` | Artifact repository |
| `PORT` | `8081` | Compose host port |
| `GHCR_USER` | empty | Personal GitHub username for registry login |

`DATABASE_VERSION` selects the existing Maven layout:
`org/aksw/data/faostat/faostat-qcl-2025-duckdb/VERSION/…-VERSION.duckdb.zst`.
The Dockerfile fetches `.sha1` alongside database and JDBC downloads and checks
both before adding artifacts to the image. Failures abort the build.
There is no local archive mode or automatic invocation of the database module.

## Publish to GHCR

Your GitHub account needs package write permission for the destination namespace.
Use a classic personal access token with `write:packages` as the login password,
authorizing organization SSO if applicable. CI can authenticate separately.

```sh
make login GHCR_USER=YOUR_GITHUB_USERNAME
make publish VERSION=0.0.2 DATABASE_VERSION=0.0.1
```

`publish` builds the selected image before pushing it. Neither `build`, `test`
nor Maven database deployment pushes images. New GHCR packages initially default
to private; change package visibility to public if anonymous pulls are intended.
The Dockerfile's source label links to the provider repository.
See [GitHub's container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Use new image release tags when mappings/configuration change; the database
version can remain fixed. Keep published data releases immutable. Kubernetes
deployments can additionally pin the resulting registry digest.

## Docker and Compose directly

```sh
docker build -t ghcr.io/provider-project/sparql-faostat-ontop:0.0.2 \
  --build-arg ENDPOINT_VERSION=0.0.2 --build-arg FAOSTAT_VERSION=0.0.1 .
docker compose config
```

The Makefile runs from its own directory, so `make -C endpoint …` from the
repository root and `make -f /absolute/path/to/endpoint/Makefile …` both work.
`make up` passes its selected image, version build arguments and port to Compose.
Direct Compose use can set `FAOSTAT_IMAGE`, `ENDPOINT_VERSION`, `FAOSTAT_VERSION`
and `DUCKDB_JDBC_VERSION` in the environment.

## Runtime and layers

The final stage inherits `ontop/ontop:5.5.0`'s non-root user, entrypoint and
healthcheck. DuckDB is mode 0444, JDBC opens it read-only, and query spill files
use `/tmp/duckdb`. The database is the first added runtime layer (`data-base`),
followed by JDBC (`endpoint-base`), then mappings, configuration and attribution.
Endpoint/data version labels are separate and come after the shared layers.

Downstream variants can build/publish `endpoint-base` and derive from its digest
for exact shared-base reuse. That target needs mappings and `ONTOP_*_FILE`
settings before it can serve a dataset. Build tools and compressed inputs remain
outside the final image. The `.dockerignore` allowlist excludes local caches and
Maven output.

The shared chart is maintained under `../../helm-charts/charts/ontop`. Select
`image.repository`, `image.tag` or `image.digest` in release values; image and
chart releases remain independent. See [the chart README](../../helm-charts/charts/ontop/README.md).

## Tests

`make check` verifies orchestration using a fake Docker CLI, including build
failure preventing a push and independent version arguments. It needs no daemon
or registry access. `make test` runs these checks, builds the configured image,
and runs five real endpoint checks
in an isolated container with network disabled and no host bind mounts. They
check observation/country-link counts, fixed-subject literal types, leading-zero
codes, non-root execution, read-only database permissions and checksum metadata.
The test container is removed afterward; no deployed endpoint is replaced.

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
