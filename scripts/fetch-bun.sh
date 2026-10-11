#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# fetch-bun.sh [OUT_DIR] [KEY]
#   KEY=base_bun  the Android Bun every release is built on (default)
#   KEY=host_bun  the same Bun version for glibc AArch64, which compiles it
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/work/bun-android}"
KEY="${2:-base_bun}"
mkdir -p "$OUT_DIR"
read -r URL ARCHIVE_SHA BINARY_SHA < <(
  python3 - "$ROOT/versions.json" "$KEY" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))[sys.argv[2]]
print(doc["url"], doc["archive_sha256"], doc["binary_sha256"])
PY
)
BUN="$OUT_DIR/bun"
if [ -x "$BUN" ] && [ "$(sha256sum "$BUN" | cut -d' ' -f1)" = "$BINARY_SHA" ]; then
  printf '%s\n' "$BUN"
  exit 0
fi
ARCHIVE="$OUT_DIR/bun.zip.new"
STAGE="$OUT_DIR/bun.new"
curl -fL --show-error --retry 3 -o "$ARCHIVE" "$URL"
printf '%s  %s\n' "$ARCHIVE_SHA" "$ARCHIVE" | sha256sum -c - >/dev/null
unzip -p "$ARCHIVE" '*/bun' > "$STAGE"
chmod 755 "$STAGE"
printf '%s  %s\n' "$BINARY_SHA" "$STAGE" | sha256sum -c - >/dev/null
if [ "${SKIP_RUN:-0}" != 1 ]; then
  "$STAGE" --revision >/dev/null
fi
mv -f "$STAGE" "$BUN"
rm -f "$ARCHIVE"
printf '%s\n' "$BUN"
