#!/usr/bin/env bash
set -euo pipefail

SOURCE="$1"
ZIG_DIR="$2"
NDK="$3"
TLS_OBJECT="$4"
OUTPUT="$5"

export ANDROID_NDK_HOME="$NDK"
export OPENCODE_TERMUX_TLS_ALIGN="$TLS_OBJECT"
cd "$SOURCE/packages/native"
# Unpacks the Zig dependencies vendored in the source archive; no network.
sh scripts/prepare-zig-deps.sh

# A hung build otherwise only ends at the CI job timeout, with nothing in the
# log: report what is still running every five minutes and give up after 45.
(
  while sleep 300; do
    echo "build-opentui: still running after $((SECONDS / 60)) min:"
    ps -eo pid,etime,args | grep -vE 'grep|ps -eo' | grep -E 'zig|uucode|ghostty' | cut -c1-200
  done
) &
WATCHDOG=$!
trap 'kill "$WATCHDOG" 2>/dev/null || true' EXIT
timeout 2700 "$ZIG_DIR/zig" build -Dlibrary-target=aarch64-linux-android -Doptimize=ReleaseFast --summary failures
cp -L "lib/aarch64-linux-android/libopentui.so" "$OUTPUT"
