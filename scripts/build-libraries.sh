#!/usr/bin/env bash
# Never configure or rebuild the existing OMNeT++ installation.
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
"$workspace/scripts/doctor.sh"
jobs="${BUILD_JOBS:-4}"
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_JOBS must be a positive integer.' >&2; exit 1; }
make -C "$INET_ROOT" makefiles
make -C "$INET_ROOT" -j"$jobs" MODE=release
make -C "$workspace/upstream/FiCo4OMNeT" makefiles
make -C "$workspace/upstream/FiCo4OMNeT" -j"$jobs" MODE=release
make -C "$workspace/upstream/CoRE4INET" -f Makefile.inet4 -j"$jobs"
make -C "$workspace/upstream/SignalsAndGateways" -f Makefile.inet4 -j"$jobs"
