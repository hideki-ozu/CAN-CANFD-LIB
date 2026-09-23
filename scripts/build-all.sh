#!/usr/bin/env bash
# Compatibility entry point: builds model libraries, preserving installed OMNeT++.
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$workspace/scripts/build-libraries.sh" "$@"
