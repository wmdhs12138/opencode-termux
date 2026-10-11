#!/data/data/com.termux/files/usr/bin/bash
# The Termux halves of the bionic job, run inside termux-docker:
#
#   bionic-build.sh natives        test, then build the four Bionic native assets
#   bionic-build.sh verify IMAGE   run the compiled candidate, then package it
#
# Between them the runner itself compiles OpenCode (scripts/compile.sh).
# Arguments, not `docker run -e`: the image's entrypoint drops the environment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PHASE="${1:?usage: bionic-build.sh natives|verify IMAGE}"
IMAGE="${2:-unknown}"
DISTRO="${ANDROID_BUILD_DISTRO:-ubuntu}"
cd "$ROOT"

# The image has no chosen mirror, so every `pkg` call picks a random one and
# rewrites sources.list; one answering 429 failed a release build. Use the
# official repository, as codex-termux does.
echo 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
export TERMUX_PKG_NO_MIRROR_SELECT=1

natives() {
  echo "::group::Install Termux build dependencies"
  pkg update -y
  pkg install -y \
    bash binutils clang coreutils curl file git make nodejs patch procps python unzip zip \
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

  make test
  ANDROID_BUILD_DISTRO="$DISTRO" make build-native

  {
    printf 'clang=%s\n' "$(clang --version | sed -n '1p')"
    printf 'rust=%s\n' "$(proot-distro login "$DISTRO" -- bash -lc '. "$HOME/.cargo/env"; rustc +1.90.0 --version')"
    dpkg-query -W -f='package=${Package} version=${Version}\n' \
      ndk-multilib ndk-multilib-native-static proot-distro
  } > work/native/BUILD-INFO.txt
}

verify() {
  # A fresh container: nothing from the natives phase is installed.
  pkg update -y
  pkg install -y coreutils make python zip
  make verify

  VERSION="$(python3 -c 'import json; print(json.load(open("dist/build-manifest.json"))["opencode"])')"
  PACKAGE="opencode-termux-v${VERSION}-android-aarch64"
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
    printf 'opencode=%s\n' "$VERSION"
    printf 'target=android-aarch64\n'
    printf 'runtime=bionic\n'
    printf 'android_api=28\n'
    printf 'termux_docker=%s\n' "$IMAGE"
    python3 - <<'PY'
import json
doc = json.load(open("dist/build-manifest.json"))
print(f"source_commit={doc['source']['commit']}")
print(f"bun={doc['base_bun']['version']}")
print(f"host_bun={doc['host_bun']['version']}")
PY
    cat work/native/BUILD-INFO.txt
  } > "$PACKAGE_DIR/BUILD-INFO.txt"

  (
    cd "$ROOT/dist/release"
    zip -0 -r "$PACKAGE.zip" "$PACKAGE"
    sha256sum "$PACKAGE.zip" > "$PACKAGE.zip.sha256"
  )
  printf '%s\n' "$PACKAGE" > "$ROOT/dist/package-name"
  printf 'bionic-build: OK: %s\n' "$ROOT/dist/release/$PACKAGE.zip"
}

case "$PHASE" in
  natives) natives ;;
  verify) verify ;;
  *) echo "bionic-build: unknown phase $PHASE" >&2; exit 2 ;;
esac
