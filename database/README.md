# FAOSTAT database artifact

Build and publish a preloaded DuckDB database from pinned FAOSTAT QCL 2025
and geographic definition artifacts. The output is `target/faostat.duckdb.zst`.

## Build

Requires Maven and a JDK (recommended: Maven 3.9.11+ / JDK 17+) and a local
Docker daemon. Run from this folder:

```sh
mvn -P local deploy
```

The `local` profile publishes to `target/m2` and skips Maven's install step,
keeping the generated dataset separate from your other Maven artifacts.
Without the profile, `mvn install` and `mvn deploy` also install it into your
configured local repository, usually `~/.m2/repository`. Source and plugin
dependencies always use Maven's configured cache.

The endpoint reads `database/target/m2` by default when present. Its
`DATABASE_REPOSITORY` setting can select another folder or disable this input;
see [endpoint configuration](../endpoint/README.md#configuration).
Override this build's publication folder with `-Dlocal.deployment.directory=/path/to/m2`.

Repeated builds reuse completed output. After changing sources, SQL or generation
settings, run `mvn -P local clean deploy`; `clean` removes all of `target/`,
including the local publication repository.

## Remote publication

Set a new version in `pom.xml` for each immutable release and configure matching
server credentials in Maven's `settings.xml`:

```sh
mvn deploy \
  -DaltDeploymentRepository=aksw-data-releases::https://maven.inf-ai.duckdns.org/releases
```

The repository override uses `id::url`. Add `-Dmaven.install.skip=true` to avoid
also installing the dataset into your normal local repository. `mvn package`
only creates the archive; it neither installs nor deploys it.

To publish an existing archive without running the generation containers:

```sh
mvn -P local -DskipGenerateData=true deploy
```

Do not combine this with `clean`, which removes the required archive.
The current coordinates are
`org.aksw.data.faostat:faostat-qcl-2025-duckdb:duckdb.zst:0.0.1`
(type `duckdb.zst`, no classifier). Database publication does not build or deploy
the endpoint.

## Generation and caching

Maven resolves inputs into `target/inputs`, then runs the DuckDB shell image
with read-only input/SQL/script mounts and `target` mounted at `/output`.
A separate small image installs zstd; its build tar contains no datasets.
The Docker daemon must see the workspace at the same absolute path.

The scripts own completion checks:

- `faostat.duckdb.complete` marks a successfully loaded raw database.
- `faostat.duckdb.zst.completed` plus a nonempty archive skips loading and compression.
- Compression writes a temporary file, validates it, renames it and writes the
  archive marker. It then removes the raw database. Failure preserves raw data
  for retry.

Markers are manual, not input fingerprints. To force generation while keeping
resolved inputs and local publications, remove both markers before rebuilding.
Use `mvn docker:stop` to remove leftover build containers after an interruption.

Useful overrides (timeouts are milliseconds):

```sh
mvn -P local deploy -Dzstd.level=3 -Dzstd.threads=2
mvn -P local deploy -Dgenerator.timeout=3600000 -Dcompressor.timeout=900000
```

Defaults: zstd level 6, two threads, 30-minute loading and 10-minute compression
timeouts. Keep `duckdb.image` compatible with the endpoint's JDBC version.
`data.repository.url` selects the source artifact repository.

## Future option: ORAS

An optional Maven profile could also publish the compressed file as an OCI data
artifact, using [ORAS](https://oras.land/docs/how_to_guides/pushing_and_pulling/).
The third-party [oras-maven-plugin](https://github.com/Tosan/oras-maven-plugin)
is a candidate; CLI and credential compatibility would need verification.
This is not implemented. Maven remains responsible for publication, local/remote
resolution, mirrors and credentials; OCI consumption would be a separate change.

## Tests

Resolve the JDBC driver, then run the fixture and script checks:

```sh
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy \
  -Dartifact=org.duckdb:duckdb_jdbc:1.5.6.0 \
  -DoutputDirectory=target/test-dependencies
python3 -m unittest discover -s tests -v
```

Tests require Python, a JDK and host zstd. Set `DUCKDB_JDBC_JAR` to use another
driver location. `sh tests/test_duckdb_shell.sh` additionally checks the shell
image using Docker.

## Sources and licence

See the [source attribution and licence](../README.md#sources-and-licence) and
[geographic policy record](../endpoint/ontop/faostat-geographic-definitions.meta.md).
The POM includes artifact metadata and pinned source coordinates.
