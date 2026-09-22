#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX_PATH="${PREFIX:-/data/data/com.termux/files/usr}"
OUT_DIR="${1:-$ROOT/work/native/opentui}"
DISTRO="${ANDROID_BUILD_DISTRO:-android-build}"
mkdir -p "$OUT_DIR"

for command_name in curl patch proot-distro clang; do
  command -v "$command_name" >/dev/null || { echo "build-opentui: $command_name is required" >&2; exit 1; }
done
[ -d "$PREFIX_PATH/aarch64-linux-android/lib" ] || {
  echo "build-opentui: install ndk-multilib and ndk-multilib-native-static" >&2
  exit 1
}

read -r VERSION SOURCE_URL SOURCE_SHA ZIG_VERSION ZIG_URL ZIG_SHA < <(
  python3 - "$ROOT/versions.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
p, z = x["opentui"], x["zig"]
print(p["version"], p["source_url"], p["source_sha256"],
      z["version"], z["aarch64_linux_url"], z["aarch64_linux_sha256"])
PY
)

fetch() {
  local url="$1" expected="$2" output="$3"
  if [ -f "$output" ] && [ "$(sha256sum "$output" | cut -d' ' -f1)" = "$expected" ]; then
    return
  fi
  curl -fL --show-error --retry 5 --retry-all-errors -C - -o "$output.new" "$url"
  printf '%s  %s\n' "$expected" "$output.new" | sha256sum -c - >/dev/null
  mv -f "$output.new" "$output"
}

SOURCE_ARCHIVE="$OUT_DIR/opentui-$VERSION.tar.gz"
ZIG_ARCHIVE="$OUT_DIR/zig-$ZIG_VERSION.tar.xz"
fetch "$SOURCE_URL" "$SOURCE_SHA" "$SOURCE_ARCHIVE"
COMMON_ZIG="$ROOT/work/toolchains/zig-$ZIG_VERSION.tar.xz"
if [ ! -f "$ZIG_ARCHIVE" ] && [ -f "$COMMON_ZIG" ] && \
   [ "$(sha256sum "$COMMON_ZIG" | cut -d' ' -f1)" = "$ZIG_SHA" ]; then
  cp -f "$COMMON_ZIG" "$ZIG_ARCHIVE"
fi
fetch "$ZIG_URL" "$ZIG_SHA" "$ZIG_ARCHIVE"

STAGE="$(mktemp -d "$OUT_DIR/.build.XXXXXX")"
trap 'rm -rf "$STAGE" "$OUT_DIR/.libopentui.new.so"' EXIT
mkdir -p "$STAGE/source" "$STAGE/zig"
tar -xzf "$SOURCE_ARCHIVE" -C "$STAGE/source" --strip-components=1
tar -xJf "$ZIG_ARCHIVE" -C "$STAGE/zig" --strip-components=1
patch -d "$STAGE/source" -p1 < "$ROOT/patches/opentui-android.patch"
clang -c -fPIC "$ROOT/native/tls-align.S" -o "$STAGE/tls-align.o"

NDK="$STAGE/termux-ndk"
HOST="$NDK/toolchains/llvm/prebuilt/linux-aarch64"
NDK_LIB="$HOST/sysroot/usr/lib/aarch64-linux-android"
mkdir -p "$NDK_LIB"
ln -s "$PREFIX_PATH/include" "$HOST/sysroot/usr/include"
for library in "$PREFIX_PATH/aarch64-linux-android/lib/"*; do
  ln -s "$library" "$NDK_LIB/$(basename "$library")"
done
ln -sf "$PREFIX_PATH/aarch64-linux-android/lib/libc++_shared.so" "$NDK_LIB/libc++.so"
ln -s . "$NDK_LIB/24"
ln -s linux-aarch64 "$NDK/toolchains/llvm/prebuilt/linux-x86_64"

proot-distro login "$DISTRO" -- bash "$ROOT/scripts/build-opentui-inner.sh" \
  "$STAGE/source" "$STAGE/zig" "$NDK" "$STAGE/tls-align.o" \
  "$OUT_DIR/.libopentui.new.so"

python3 "$ROOT/tools/elf_native.py" "$OUT_DIR/.libopentui.new.so" >/dev/null
"$ROOT/work/bun-android/bun" "$ROOT/tools/opentui_smoke.ts" \
  "$OUT_DIR/.libopentui.new.so" > "$OUT_DIR/smoke.json"
mv -f "$OUT_DIR/.libopentui.new.so" "$OUT_DIR/libopentui.so"
sha256sum "$OUT_DIR/libopentui.so" | cut -d' ' -f1 > "$OUT_DIR/libopentui.so.sha256"
printf 'build-opentui: OK: %s\n' "$OUT_DIR/libopentui.so"
