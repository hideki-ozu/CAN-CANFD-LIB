#!/usr/bin/env bash
# Optional: unpacks the OpenSSL development headers matching the installed libssl3
# into .local/openssl-dev when libssl-dev cannot be installed. Nothing is installed
# into the host OS and sudo is never used. Debian/Ubuntu (apt-get, dpkg) only.
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(dpkg-query -W -f='${Version}' libssl3t64 2>/dev/null || dpkg-query -W -f='${Version}' libssl3)"
[[ -n "$version" ]] || { echo 'libssl3 is not installed; cannot select matching headers.' >&2; exit 1; }
download_dir="$workspace/downloads/openssl-dev"
target="$workspace/.local/openssl-dev"
mkdir -p "$download_dir"
(cd "$download_dir" && apt-get download "libssl-dev=$version")
rm -rf "$target"
dpkg-deb -x "$download_dir/libssl-dev_${version//:/%3a}_"*.deb "$target"
echo "OpenSSL $version headers are in $target (scripts/env.sh uses them automatically)."
