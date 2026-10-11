#!/data/data/com.termux/files/usr/bin/bash
# Build the Termux-side native assets (watcher, FFF, bun-pty) and export the
# Android sysroot; run by bionic-build.sh after `pkg update`. The workflow
# caches what this produces under a hash of this file and the assets' own
# inputs, so everything that shapes them belongs here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DISTRO="${ANDROID_BUILD_DISTRO:-ubuntu}"
cd "$ROOT"

echo "::group::Install Termux build dependencies"
pkg install -y binutils clang nodejs procps proot-distro ndk-multilib ndk-multilib-native-static
echo "::endgroup::"

echo "::group::Prepare glibc host tools"
if ! proot-distro login "$DISTRO" -- true >/dev/null 2>&1; then
  proot-distro install "$DISTRO"
fi
proot-distro login "$DISTRO" -- bash -lc '
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl pkg-config
  if [ ! -f "$HOME/.cargo/env" ]; then
    curl --proto "=https" --tlsv1.2 -fsSL https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain none
  fi
  . "$HOME/.cargo/env"
  rustup toolchain install 1.90.0 --profile minimal --target aarch64-linux-android
'
echo "::endgroup::"

ANDROID_BUILD_DISTRO="$DISTRO" make build-native

{
  printf 'clang=%s\n' "$(clang --version | sed -n '1p')"
  printf 'rust=%s\n' "$(proot-distro login "$DISTRO" -- bash -lc '. "$HOME/.cargo/env"; rustc +1.90.0 --version')"
  dpkg-query -W -f='package=${Package} version=${Version}\n' \
    ndk-multilib ndk-multilib-native-static proot-distro
} > work/native/BUILD-INFO.txt
