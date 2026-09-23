#!/usr/bin/env bash
set -euo pipefail

# Download and unpack build dependencies under this workspace. No package is
# installed into the host OS and sudo is never used.
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
download_dir="$workspace/downloads/runtime-debs"
deps_dir="$workspace/.local/runtime-deps"
mkdir -p "$download_dir" "$deps_dir"

packages=(
  bison flex libfl2 m4 libsigsegv2 pkg-config pkgconf pkgconf-bin libpkgconf3
  qt6-base-dev qt6-base-dev-tools qmake6 qmake6-bin qt6-qpa-plugins
  libqt6concurrent6t64 libqt6core6t64 libqt6dbus6t64 libqt6gui6t64
  libqt6network6t64 libqt6opengl6t64 libqt6openglwidgets6t64
  libqt6printsupport6t64 libqt6sql6t64 libqt6test6t64 libqt6widgets6t64
  libqt6xml6t64 libdouble-conversion3 libb2-1 libpcre2-16-0 libmd4c0
  qt6-svg-dev libqt6svg6 libqt6svgwidgets6
  libgl-dev libglx-dev libopengl-dev libvulkan-dev
)

(
  cd "$download_dir"
  apt-get download "${packages[@]}"
  for package in ./*.deb; do
    dpkg-deb -x "$package" "$deps_dir"
  done
)

echo "Local runtime dependencies are in $deps_dir"
