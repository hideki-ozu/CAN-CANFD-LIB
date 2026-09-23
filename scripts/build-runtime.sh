#!/usr/bin/env bash
set -euo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export OMNETPP_ROOT="$workspace/tools/omnetpp-6.4.0"
source "$workspace/scripts/env.sh"
build_jobs="${BUILD_JOBS:-8}"

cd "$OMNETPP_ROOT"
if [ ! -x .venv/bin/python3 ]; then
    uv venv .venv
    uv pip install --python .venv/bin/python3 -r python/requirements.txt
fi
# Activate a newly created venv and reapply local tool paths.
source "$workspace/scripts/env.sh"
cp "$workspace/scripts/configure.user.runtime" configure.user
./configure
make -j"$build_jobs" MODE=release

cd "$INET_ROOT"
make makefiles
make -j"$build_jobs" MODE=release
