#!/usr/bin/env bash
# Read-only preflight for the pinned release profile.
set -euo pipefail
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$workspace/scripts/env.sh"
if [[ "$(uname -s)" != Linux ]]; then
    echo 'This setup supports Linux/WSL2. Native Windows/macOS are not validated.' >&2
    exit 1
fi
if [[ "$workspace" =~ [[:space:]] || "$OMNETPP_ROOT" =~ [[:space:]] ]]; then
    echo 'OMNeT++ makefiles require repository and OMNeT++ paths without whitespace.' >&2
    exit 1
fi
if [[ ! -f "$OMNETPP_ROOT/Makefile.inc" ]]; then
    echo "OMNeT++ is not configured/built: $OMNETPP_ROOT" >&2
    exit 1
fi
version="$(tr -d '\r\n' < "$OMNETPP_ROOT/Version")"
if [[ "$version" != omnetpp-6.4.0 ]]; then
    echo "This pinned profile requires OMNeT++ 6.4.0; detected $version. Existing installation was not changed." >&2
    exit 1
fi
for tool in git make python3 opp_run opp_makemake opp_msgc; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
python3 - <<'PY'
import os, pathlib, re, shlex, shutil, sys
if sys.version_info < (3, 10):
    sys.exit('Python 3.10 or newer is required.')
config = (pathlib.Path(os.environ['OMNETPP_ROOT']) / 'Makefile.inc').read_text()
if not re.search(r'^SHARED_LIBS\s*=\s*yes\s*$', config, re.M):
    sys.exit('OMNeT++ must have shared libraries enabled for dynamic model loading.')
compiler = re.search(r'^CXX\s*=\s*(.+)$', config, re.M)
if not compiler:
    sys.exit('Cannot determine the compiler from OMNeT++ Makefile.inc.')
for token in shlex.split(compiler.group(1)):
    if token.startswith('-'):
        break
    if not shutil.which(token):
        sys.exit(f'Compiler/tool used by this OMNeT++ is unavailable: {token}')
print('Compiler:', compiler.group(1))
PY
# Executes the installed runtime and detects unresolved shared libraries.
opp_run -h >/dev/null
# SecOC uses OpenSSL 3 libcrypto (EVP_MAC CMAC). Compile, link and run a probe.
probe_dir="$(mktemp -d)"
trap 'rm -rf "$probe_dir"' EXIT
cat > "$probe_dir/probe.c" <<'C'
#include <openssl/evp.h>
#if OPENSSL_VERSION_MAJOR < 3
#error OpenSSL 3 is required
#endif
int main(void) { EVP_MAC *m = EVP_MAC_fetch(NULL, "CMAC", NULL); int ok = m != NULL; EVP_MAC_free(m); return !ok; }
C
# shellcheck disable=SC2086
if ! cc $OPENSSL_CFLAGS "$probe_dir/probe.c" -o "$probe_dir/probe" $OPENSSL_LIBS 2>"$probe_dir/log" || ! "$probe_dir/probe"; then
    cat "$probe_dir/log" >&2
    echo 'OpenSSL 3 development files (libcrypto with CMAC) are required for SecOC.' >&2
    echo 'Install libssl-dev (Debian/Ubuntu) or openssl-devel, set OPENSSL_CFLAGS/OPENSSL_LIBS,' >&2
    echo 'or run scripts/fetch-openssl-dev.sh to unpack matching headers into .local/ without sudo.' >&2
    exit 1
fi
echo "OpenSSL: ${OPENSSL_CFLAGS:-system headers} $OPENSSL_LIBS"
printf 'OMNeT++: %s\nVersion: %s\nPreflight: OK\n' "$OMNETPP_ROOT" "$version"
