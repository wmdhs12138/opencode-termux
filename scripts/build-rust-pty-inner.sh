#!/usr/bin/env bash
set -euo pipefail

ROOT="$1"
SOURCE="$2"
TARGET_DIR="$3"
TLS_OBJECT="$4"
LINKER="$ROOT/scripts/android-clang"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"

command -v cargo >/dev/null || { echo "build-rust-pty: cargo is missing in the build container" >&2; exit 1; }
rustup target list --installed | grep -Fx aarch64-linux-android >/dev/null || {
  echo "build-rust-pty: install rustup target aarch64-linux-android in the build container" >&2
  exit 1
}

export CARGO_TARGET_DIR="$TARGET_DIR"
export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="$LINKER"
export RUSTFLAGS="-C link-arg=$TLS_OBJECT -C link-arg=-Wl,-z,max-page-size=16384"
cd "$SOURCE/rust-pty"
cargo update -p portable-pty --precise 0.9.0
cargo build --release --locked --target aarch64-linux-android
cp -L "$TARGET_DIR/aarch64-linux-android/release/librust_pty.so" "$ROOT/work/native/rust-pty.new.so"
