#!/usr/bin/env bash
# Fetch pinned model sources, build against existing OMNeT++, run acceptance tests.
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
"$workspace/scripts/doctor.sh"
mkdir -p "$workspace/.local" "$workspace/logs"
# Store only a literal path, never source this file as shell code.
printf '%s\n' "$OMNETPP_ROOT" > "$workspace/.local/omnetpp-root"
python3 "$workspace/scripts/fetch-sources.py"
"$workspace/scripts/build-libraries.sh"
python3 "$workspace/tests/test_canfd.py"
python3 "$workspace/tests/test_mixed.py"
python3 "$workspace/tests/test_avtp.py"
python3 "$workspace/tests/test_someip.py"
python3 "$workspace/tests/test_protection.py"
python3 "$workspace/tests/test_av.py"
printf '\nSetup and validation passed. GUI: ./scripts/run-gui.sh Mixed\n'
