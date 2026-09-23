#!/usr/bin/env bash
set -euo pipefail

: "${OMNETPP_LOCAL_DEPS:?Source scripts/env.sh before invoking this wrapper.}"
qmake="$OMNETPP_LOCAL_DEPS/usr/lib/qt6/bin/qmake6"

if [[ "${1:-}" == "-query" ]]; then
    "$qmake" "$@" | sed "s|^/usr|$OMNETPP_LOCAL_DEPS/usr|"
else
    exec "$qmake" "$@"
fi
