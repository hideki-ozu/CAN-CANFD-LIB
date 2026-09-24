#!/usr/bin/env bash
# Opens examples/someip in Qtenv (press Run).
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
if [[ ! -f "$OMNETPP_ROOT/lib/liboppqtenv.so" ]]; then
    echo "Qtenv is not available in this OMNeT++ installation. Use scripts/run-someip.sh for CLI." >&2
    exit 1
fi
config="${1:-SomeIpTcpUdp}"
if (($#)); then shift; fi
exec "$workspace/scripts/run-someip.sh" "$config" -u Qtenv \
    -l "$OMNETPP_ROOT/lib/liboppqtenv.so" \
    --qtenv-default-config="$config" --qtenv-default-run=0 "$@"
