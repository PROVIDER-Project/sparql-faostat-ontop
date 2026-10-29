#!/bin/sh
# Best-effort check of known local manifest digests in the destination repository.
set -eu
docker=${1:?Docker executable required}
image=${2:?Image reference required}
report=$(mktemp)
trap 'rm -f "$report"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! references=$("$docker" image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image"); then
    printf '%s\n' "Cannot inspect the built image; refusing to push $image" >&2
    exit 1
fi
# A local image ID is not generally a registry manifest digest. Never use it as one.
digests=$(printf '%s\n' "$references" | sed -n 's/^.*@\(sha256:[0-9a-f]\{64\}\)$/\1/p' | sort -u)
if [ -z "$digests" ]; then
    printf '%s\n' 'No local manifest digest available; skipping the best-effort digest check.'
    exit 0
fi

repository=${image%%@*}
# Strip a tag only from the final path component; preserve registry port numbers.
case "${repository##*/}" in *:*) repository=${repository%:*} ;; esac
for digest in $digests; do
    reference="$repository@$digest"
    if "$docker" manifest inspect "$reference" >"$report" 2>&1; then
        printf '%s\n' "Refusing to republish an image manifest already present remotely: $reference" >&2
        printf '%s\n' 'The image was built locally, but nothing was pushed.' >&2
        printf '%s\n' 'Rebuild changed image content before publishing; changing only the tag is not enough.' >&2
        exit 1
    fi
    if LC_ALL=C grep -Eiq '(^|: |\[)(no such manifest:|manifest unknown|MANIFEST_UNKNOWN)' "$report"; then
        continue
    fi
    printf '%s\n' "Could not check remote manifest: $reference" >&2
    cat "$report" >&2
    printf '%s\n' 'Check registry credentials/connectivity and retry; nothing was pushed.' >&2
    exit 1
done
printf '%s\n' 'Known image manifest digests are absent from the destination repository.'
