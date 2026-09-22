#!/usr/bin/env bash
set -euo pipefail

ROOT="$1"
SOURCE="$2"
TARGET_DIR="$3"
TLS_OBJECT="$4"
OUTPUT="$5"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"

CC="$ROOT/scripts/android-clang"
CXX="$ROOT/scripts/android-clang++"

command -v cargo >/dev/null || { echo "build-fff: cargo is missing in the build container" >&2; exit 1; }
rustup target list --installed --toolchain 1.90.0 | grep -Fx aarch64-linux-android >/dev/null || {
  echo "build-fff: Rust 1.90.0 Android target is missing in the build container" >&2
  exit 1
}

export CARGO_TARGET_DIR="$TARGET_DIR"
export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="$CC"
export CC_aarch64_linux_android="$CC"
export CXX_aarch64_linux_android="$CXX"
export AR_aarch64_linux_android="$TERMUX_PREFIX/bin/llvm-ar"
export RUSTFLAGS="-C link-arg=$TLS_OBJECT -C link-arg=-Wl,-z,max-page-size=16384"

cd "$SOURCE"
cargo +1.90.0 build --release --locked --target aarch64-linux-android -p fff-c
cp -L "$TARGET_DIR/aarch64-linux-android/release/libfff_c.so" "$OUTPUT"
