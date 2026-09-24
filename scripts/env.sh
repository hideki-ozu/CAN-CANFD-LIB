#!/usr/bin/env bash
# Source from bash. OMNETPP_ROOT overrides the saved setup path and autodetection.
_can_workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_can_root="${OMNETPP_ROOT:-}"
if [[ -z "$_can_root" && -f "$_can_workspace/.local/omnetpp-root" ]]; then
    IFS= read -r _can_root < "$_can_workspace/.local/omnetpp-root"
fi
if [[ -z "$_can_root" ]]; then
    _can_root="${__omnetpp_root_dir:-}"
fi
if [[ -z "$_can_root" ]] && command -v opp_run >/dev/null 2>&1; then
    _can_root="$(dirname "$(dirname "$(command -v opp_run)")")"
fi
if [[ -z "$_can_root" ]]; then
    _can_root="$_can_workspace/tools/omnetpp-6.4.0"
fi
if [[ ! -f "$_can_root/setenv" ]]; then
    echo 'Built OMNeT++ not found. Source its setenv or export OMNETPP_ROOT=/path/to/omnetpp-6.4.0.' >&2
    return 1
fi
export OMNETPP_ROOT="$(cd "$_can_root" && pwd)"
export INET_ROOT="$_can_workspace/upstream/inet"
case $- in
    *u*) _can_restore_nounset=1; set +u ;;
    *) _can_restore_nounset=0 ;;
esac
# OMNeT++ activates its own Python environment; augment paths afterwards.
source "$OMNETPP_ROOT/setenv" -q
_can_source_status=$?
if [[ "$_can_restore_nounset" == 1 ]]; then set -u; fi
if [[ "$_can_source_status" != 0 ]]; then return "$_can_source_status"; fi
# Private Qt/build dependencies belong only to the optional bundled runtime.
if [[ "$OMNETPP_ROOT" == "$_can_workspace/tools/omnetpp-6.4.0" && -d "$_can_workspace/.local/runtime-deps" ]]; then
    export OMNETPP_LOCAL_DEPS="$_can_workspace/.local/runtime-deps"
    export PATH="$OMNETPP_LOCAL_DEPS/usr/bin:$OMNETPP_LOCAL_DEPS/usr/lib/qt6/bin:$PATH"
    export LD_LIBRARY_PATH="$OMNETPP_LOCAL_DEPS/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
    export BISON_PKGDATADIR="$OMNETPP_LOCAL_DEPS/usr/share/bison"
    export M4="$OMNETPP_LOCAL_DEPS/usr/bin/m4"
    export QT_PLUGIN_PATH="$OMNETPP_LOCAL_DEPS/usr/lib/x86_64-linux-gnu/qt6/plugins${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
fi
# OpenSSL libcrypto for SecOC (AES-128-CMAC). Explicit OPENSSL_CFLAGS/OPENSSL_LIBS win;
# otherwise headers unpacked by scripts/fetch-openssl-dev.sh, else the system package.
if [[ -z "${OPENSSL_CFLAGS+x}" && -f "$_can_workspace/.local/openssl-dev/usr/include/openssl/evp.h" ]]; then
    _can_ssl="$_can_workspace/.local/openssl-dev/usr/include"
    export OPENSSL_CFLAGS="-I$_can_ssl"
    for _can_arch in "$_can_ssl"/*/openssl/configuration.h; do
        [[ -f "$_can_arch" ]] && OPENSSL_CFLAGS="$OPENSSL_CFLAGS -I$(dirname "$(dirname "$_can_arch")")"
    done
    # The unpacked libcrypto.so link is dangling; link the installed runtime library.
    export OPENSSL_LIBS="${OPENSSL_LIBS:--l:libcrypto.so.3}"
    unset _can_ssl _can_arch
fi
export OPENSSL_CFLAGS="${OPENSSL_CFLAGS:-}"
export OPENSSL_LIBS="${OPENSSL_LIBS:--lcrypto}"
export AUTOSAR_ROOT="$_can_workspace/autosar"
export PATH="$OMNETPP_ROOT/bin:$INET_ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$OMNETPP_ROOT/lib:$INET_ROOT/src:$AUTOSAR_ROOT/src:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$OMNETPP_ROOT/python:$INET_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
export OMNETPP_IMAGE_PATH="$INET_ROOT/images${OMNETPP_IMAGE_PATH:+:$OMNETPP_IMAGE_PATH}"
export INET_OMNETPP_OPTIONS="--image-path=$INET_ROOT/images"
unset _can_workspace _can_root _can_restore_nounset _can_source_status
