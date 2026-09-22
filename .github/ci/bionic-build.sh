#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${OPENCODE_VERSION_INPUT:-latest}"
DISTRO="${ANDROID_BUILD_DISTRO:-ubuntu}"

echo "::group::Install Termux build dependencies"
pkg update -y
pkg install -y \
  bash binutils clang coreutils curl file git make nodejs patch python unzip zip \
  proot-distro ndk-multilib ndk-multilib-native-static
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

cd "$ROOT"
make test
make fetch VERSION="$VERSION"
ANDROID_BUILD_DISTRO="$DISTRO" make build-strict

ACTUAL_VERSION="$(tr -d '[:space:]' < work/upstream/version)"
PACKAGE="opencode-termux-v${ACTUAL_VERSION}-android-aarch64"
PACKAGE_DIR="$ROOT/dist/release/$PACKAGE"
rm -rf "$ROOT/dist/release"
mkdir -p "$PACKAGE_DIR"
cp "$ROOT/dist/opencode" "$PACKAGE_DIR/opencode"
cp "$ROOT/dist/build-manifest.json" "$PACKAGE_DIR/BUILD-MANIFEST.json"
cp "$ROOT/dist/build-manifest.json" "$ROOT/dist/release/build-manifest.json"
cp "$ROOT/LICENSE" "$PACKAGE_DIR/LICENSE"
cp "$ROOT/THIRD_PARTY.md" "$PACKAGE_DIR/THIRD_PARTY.md"
chmod 755 "$PACKAGE_DIR/opencode"

(
  cd "$PACKAGE_DIR"
  sha256sum opencode > SHA256SUMS
)

{
  printf 'opencode=%s\n' "$ACTUAL_VERSION"
  printf 'target=android-aarch64\n'
  printf 'runtime=bionic\n'
  printf 'android_api=28\n'
  printf 'termux_docker=%s\n' "${TERMUX_DOCKER_IMAGE:-unknown}"
  printf 'bun=%s\n' "$(python3 -c 'import json; print(json.load(open("versions.json"))["base_bun"]["version"])')"
  printf 'clang=%s\n' "$(clang --version | sed -n '1p')"
  printf 'rust=%s\n' "$(proot-distro login "$DISTRO" -- bash -lc '. "$HOME/.cargo/env"; rustc +1.90.0 --version')"
  dpkg-query -W -f='package=${Package} version=${Version}\n' \
    ndk-multilib ndk-multilib-native-static proot-distro
} > "$PACKAGE_DIR/BUILD-INFO.txt"

(
  cd "$ROOT/dist/release"
  zip -0 -r "$PACKAGE.zip" "$PACKAGE"
  sha256sum "$PACKAGE.zip" > "$PACKAGE.zip.sha256"
)
printf '%s\n' "$PACKAGE" > "$ROOT/dist/package-name"
printf 'bionic-build: OK: %s\n' "$ROOT/dist/release/$PACKAGE.zip"
