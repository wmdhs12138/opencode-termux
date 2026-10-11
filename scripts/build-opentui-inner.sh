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
"$ZIG_DIR/zig" build -Dlibrary-target=aarch64-linux-android -Doptimize=ReleaseFast
cp -L "lib/aarch64-linux-android/libopentui.so" "$OUTPUT"
