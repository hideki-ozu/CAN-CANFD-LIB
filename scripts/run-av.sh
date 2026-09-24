#!/usr/bin/env bash
set -eo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
set -u
config="${1:-AvBasic}"
if (($#)); then shift; fi
mkdir -p "$workspace/results/av/$config"
cd "$workspace/examples/av"
exec opp_run -u Cmdenv \
    -n "$workspace/examples:$INET_ROOT/src:$workspace/upstream/FiCo4OMNeT/src:$workspace/upstream/CoRE4INET/src-inet4:$workspace/upstream/SignalsAndGateways/src-inet4" \
    -l "$INET_ROOT/src/INET" \
    -l "$workspace/upstream/FiCo4OMNeT/src/FiCo4OMNeT" \
    -l "$workspace/upstream/CoRE4INET/out-inet4/CoRE4INET_INET4" \
    -l "$workspace/upstream/SignalsAndGateways/src-inet4/SignalsAndGateways_INET4" \
    -f omnetpp.ini -c "$config" \
    --result-dir="$workspace/results/av/$config" "$@"
