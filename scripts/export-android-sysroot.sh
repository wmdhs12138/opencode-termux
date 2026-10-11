#!/data/data/com.termux/files/usr/bin/bash
# Copy the Android sysroot that Termux's ndk-sysroot and ndk-multilib packages
# provide into the workspace, laid out like the NDK, for scripts/build-opentui.sh
# on the glibc host. Copies, not symlinks: the host has no Termux prefix.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX_PATH="${PREFIX:-/data/data/com.termux/files/usr}"
OUT="${1:-$ROOT/work/android-ndk}"
SYSROOT="$OUT/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr"

[ -d "$PREFIX_PATH/aarch64-linux-android/lib" ] && [ -f "$PREFIX_PATH/include/stdio.h" ] || {
  echo "export-android-sysroot: install ndk-sysroot, ndk-multilib and ndk-multilib-native-static" >&2
  exit 1
}

rm -rf "$OUT.new"
mkdir -p "$OUT.new/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib"
cp -RL "$PREFIX_PATH/include" "$OUT.new/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/include"
LIB="$OUT.new/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android"
cp -RL "$PREFIX_PATH/aarch64-linux-android/lib" "$LIB"
ln -sf libc++_shared.so "$LIB/libc++.so"
# The crt objects of the API level the libraries were built for.
ln -s . "$LIB/24"
rm -rf "$OUT"
mv "$OUT.new" "$OUT"
printf 'export-android-sysroot: OK: %s (%s)\n' "$SYSROOT" "$(du -sh "$OUT" | cut -f1)"
