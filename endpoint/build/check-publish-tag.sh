#!/bin/sh
# Check only the remote reference; local images may always be replaced by build.
set -eu
docker=${1:?Docker executable required}
image=${2:?Image reference required}
endpoint_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
report=$(mktemp)
trap 'rm -f "$report"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if "$docker" manifest inspect "$image" >"$report" 2>&1; then
    printf '%s\n' "Refusing to overwrite existing remote image: $image" >&2
    printf '%s\n' "Set a new VERSION in $endpoint_dir/build.conf, or run:" >&2
    printf '  make -C "%s" publish VERSION=NEW_VERSION\n' "$endpoint_dir" >&2
    printf '%s\n' 'If IMAGE is explicitly overridden, choose a new tag in IMAGE too.' >&2
    exit 1
fi

# Do not interpret authentication, transport, rate-limit or other failures as absence.
# Docker exposes registry errors as text; accept only explicit missing-manifest errors.
if LC_ALL=C grep -Eiq '(^|: |\[)(no such manifest:|manifest unknown|MANIFEST_UNKNOWN)' "$report"; then
    printf '%s\n' "Remote tag not found; publishing $image"
    exit 0
fi

printf '%s\n' "Could not establish whether remote image exists: $image" >&2
cat "$report" >&2
printf '%s\n' 'Check registry credentials/connectivity and retry; nothing was built or pushed.' >&2
exit 1
