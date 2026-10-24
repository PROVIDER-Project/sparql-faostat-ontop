#!/bin/sh
# Run only in the disposable Maven helper container, as the host user.
set -eu
group=${1:?groupId required}
artifact=${2:?artifactId required}
version=${3:?version required}
type=${4:?artifact type required}
output=${5:?output filename required}
case "$group:$artifact:$version:$type:$output" in
    *[!A-Za-z0-9_.:-]*) echo 'Unexpected character in artifact coordinates/output name' >&2; exit 1 ;;
esac
mkdir -p /tmp/maven-home /tmp/resolved
set -- --batch-mode --no-transfer-progress --strict-checksums \
    --global-settings /opt/build/maven-settings.xml \
    -Dmaven.repo.local=/maven-cache
if [ -f /tmp/maven-home/.m2/settings.xml ]; then
    set -- "$@" --settings /tmp/maven-home/.m2/settings.xml
fi
if [ "${MAVEN_OFFLINE:-false}" = true ]; then
    set -- "$@" --offline
fi
mvn "$@" org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy \
    "-Dartifact=$group:$artifact:$version:$type" \
    -DoutputDirectory=/tmp/resolved -Dmdep.overWriteReleases=true
mv "/tmp/resolved/$artifact-$version.$type" "/artifacts/$output"
sha1sum "/artifacts/$output" | cut -d ' ' -f 1 > "/artifacts/$output.sha1"
chmod 0644 "/artifacts/$output" "/artifacts/$output.sha1"
touch -d @0 "/artifacts/$output" "/artifacts/$output.sha1"
