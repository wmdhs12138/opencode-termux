#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-latest}"
OUT_DIR="${2:-$ROOT/work/upstream}"
mkdir -p "$OUT_DIR"

if [ "$VERSION" = latest ]; then
  API="https://api.github.com/repos/anomalyco/opencode/releases/latest"
else
  VERSION="${VERSION#v}"
  API="https://api.github.com/repos/anomalyco/opencode/releases/tags/v$VERSION"
fi

META="$OUT_DIR/release.json.new"
API_ARGS=(-fsSL --retry 5 --retry-all-errors)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  API_ARGS+=(-H "Authorization: Bearer $GITHUB_TOKEN" -H "X-GitHub-Api-Version: 2022-11-28")
fi
curl "${API_ARGS[@]}" -o "$META" "$API"
read -r TAG URL EXPECTED_SHA < <(
  python3 - "$META" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
asset = next((a for a in doc.get("assets", []) if a.get("name") == "opencode-linux-arm64.tar.gz"), None)
if not asset:
    raise SystemExit("release has no opencode-linux-arm64.tar.gz")
digest = asset.get("digest", "")
if not digest.startswith("sha256:"):
    raise SystemExit("release asset has no SHA-256 digest")
print(doc["tag_name"], asset["browser_download_url"], digest.split(":", 1)[1])
PY
)
VERSION="${TAG#v}"
ARCHIVE="$OUT_DIR/opencode-$VERSION-linux-arm64.tar.gz"
STAGE="$OUT_DIR/.opencode-$VERSION.new"
curl -fL --show-error --retry 3 -o "$ARCHIVE.new" "$URL"
ACTUAL_SHA="$(sha256sum "$ARCHIVE.new" | cut -d' ' -f1)"
[ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] || {
  echo "fetch-opencode: SHA-256 mismatch" >&2
  exit 1
}
mv -f "$ARCHIVE.new" "$ARCHIVE"
ENTRY="$(tar -tzf "$ARCHIVE" | awk '/(^|\/)opencode$/ {print}' | head -n1)"
[ -n "$ENTRY" ] || { echo "fetch-opencode: archive contains no opencode binary" >&2; exit 1; }
tar -xOzf "$ARCHIVE" "$ENTRY" > "$STAGE"
chmod 755 "$STAGE"
python3 "$ROOT/tools/extract_graph.py" "$STAGE" "$OUT_DIR/.opencode-$VERSION.graph" >/dev/null
rm -f "$OUT_DIR/.opencode-$VERSION.graph"
mv -f "$STAGE" "$OUT_DIR/opencode"
mv -f "$META" "$OUT_DIR/release.json"
printf '%s\n' "$VERSION" > "$OUT_DIR/version"
printf '%s\n' "$OUT_DIR/opencode"
