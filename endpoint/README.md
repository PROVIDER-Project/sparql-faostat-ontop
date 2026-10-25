# FAOSTAT Ontop endpoint

Package the preloaded FAOSTAT database, JDBC driver and mappings into an Ontop
image. Startup requires no data download or ingestion.

## Build and run

Requires GNU Make and Docker with BuildKit/Compose. From this folder:

```sh
make build
make up
```

The database is resolved from `../database/target/m2` by default when present,
with a separate Maven cache and remote repositories available too. To populate
that project-local repository first:

```sh
mvn -f ../database/pom.xml -P local deploy
```

The `local` profile skips installation into your normal Maven repository,
keeping the generated dataset separate from other artifacts. Without it,
`mvn install` and `mvn deploy` also install the dataset into the configured
local repository (usually `~/.m2/repository`).

The service runs at [localhost:8081/sparql](http://localhost:8081/sparql).
`make up` builds before starting; `make down` stops it. Use `make help` for all
targets and `make show-config` to inspect settings.

## Configuration

Override settings on Make's command line, through the environment, or in an
optional `.env` file (copy `.env.example`; use unquoted Make assignments).
Command-line values take precedence over `.env`, then environment values.

```sh
make build DATABASE_REPOSITORY=/path/to/m2
make build VERSION=0.0.2 DATABASE_VERSION=0.0.1
```

| Variable | Default / purpose |
| --- | --- |
| `DATABASE_REPOSITORY` | `../database/target/m2`; set empty to disable |
| `M2_DIR` | `.cache/maven`; contains the writable `repository/` cache |
| `M2_SETTINGS` | `~/.m2/settings.xml` |
| `M2_SECURITY` | `~/.m2/settings-security.xml` |
| `DATA_REPOSITORY_URL` | `https://maven.inf-ai.duckdns.org/releases` |
| `VERSION` / `DATABASE_VERSION` | Independent endpoint/database versions; both `0.0.1` |
| `DUCKDB_JDBC_VERSION` | `1.5.6.0`; keep compatible with the database |
| `REPOSITORY` | `ghcr.io/provider-project/sparql-faostat-ontop` |
| `IMAGE` | `$(REPOSITORY):$(VERSION)` |
| `PORT` | `8081` |

The publication folder is read-only; `M2_DIR` is a separate writable cache.
To resolve a normal host Maven installation instead:

```sh
make build M2_DIR="$HOME/.m2" DATABASE_REPOSITORY=
```

Existing settings/security files are mounted read-only into the Maven helper.
Mirrors, profiles and credentials apply; cache/settings files stay out of image
layers. A broad `mirrorOf=*` needs an exclusion such as `*,!faostat-local-build`
to allow direct reads from the project-local publication repository.

Maven uses cached releases first, so publish changed data under a new version.
`MAVEN_OFFLINE=true` works after all artifacts and plugins have been cached;
even a file repository needs an initial normal resolution.

## Publish to GHCR

```sh
make login GHCR_USER=YOUR_GITHUB_USERNAME
make publish VERSION=0.0.2 DATABASE_VERSION=0.0.1
```

`publish` builds then pushes; `build` alone stays local. Authenticate with a
GitHub token that can write packages and choose public package visibility if
anonymous pulls are needed. See [GitHub's registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
Use new endpoint versions for mapping/configuration changes; the database
version can stay fixed.

## Design and storage

`make resolve` runs a disposable Maven container to copy the database and JDBC
artifacts into `target/artifacts`; `make build` resolves before Docker packaging.
The helper uses your UID/GID. It does not generate or publish the database.
Direct `docker build` requires an earlier `make resolve`.

The image expands the database into its first added runtime layer, followed by
JDBC, mappings and configuration. Ontop runs as a non-root user; DuckDB is
read-only and spill files use `/tmp/duckdb`. Allow about 859 MiB for the expanded
database, plus runtime and build cache.

Maven downloads live in `.cache/maven/repository`; staged files live in
`target/artifacts`. Docker manages image layers and its build cache separately.
Cleaning the database project removes its publication folder, but leaves the
endpoint cache intact. Avoid concurrent builds sharing an output folder.

For Kubernetes, use the sibling [Ontop Helm chart](../../helm-charts/charts/ontop/README.md)
and select the published image tag or digest.

## Tests

`make check` runs orchestration checks without Docker. `make test` also builds
the image and checks SPARQL results, types, country links and runtime permissions
in an isolated container. Python 3 is required.

## Sources and licence

See the [source attribution and licence](../README.md#sources-and-licence).
Attribution and geographic provenance are also included in the image.

Project material is [Apache-2.0 licensed](LICENSE). See [licensing notes](LICENSING.md)
for third-party/data terms and the AI-assisted provenance of that information.
The image includes these files under `/opt/ontop/licenses/`.
