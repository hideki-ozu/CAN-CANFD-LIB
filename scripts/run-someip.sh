#!/usr/bin/env bash
# Runs examples/someip (SOA4CoRE INET4 port: SOME/IP, SOME/IP-SD) in Cmdenv.
set -eo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
set -u
config="${1:-SomeIpTcpUdp}"
if (($#)); then shift; fi
mkdir -p "$workspace/results/someip/$config"
cd "$workspace/examples/someip"
exec opp_run -u Cmdenv \
    -n "$workspace/examples:$INET_ROOT/src:$workspace/upstream/SOA4CoRE/src-inet4" \
    -l "$INET_ROOT/src/INET" \
    -l "$workspace/upstream/SOA4CoRE/src-inet4/SOA4CoRE_INET4" \
    -f omnetpp.ini -c "$config" \
    --result-dir="$workspace/results/someip/$config" "$@"
