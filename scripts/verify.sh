#!/data/data/com.termux/files/usr/bin/bash
# Run the compiled candidate inside Termux and promote it to dist/opencode.
#
# scripts/compile.sh builds on a glibc host that cannot execute the Android
# binary; this is where it runs for the first time: version, the injected
# update command, FFF search through the bundled wrapper, and the real TUI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
WORK="$ROOT/work/build"
CANDIDATE="$DIST/.opencode.new"
SMOKE_SECONDS="${SMOKE_SECONDS:-15}"
mkdir -p "$WORK"

[ -x "$CANDIDATE" ] && [ -f "$DIST/compile.json" ] || {
  echo "verify: no compiled candidate in $DIST (scripts/compile.sh)" >&2
  exit 1
}
[ -e /system/bin/linker64 ] || { echo "verify: run this inside Termux" >&2; exit 1; }
VERSION="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["opencode"])' "$DIST/compile.json")"
SHA="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["output_sha256"])' "$DIST/compile.json")"
[ "$(sha256sum "$CANDIDATE" | cut -d' ' -f1)" = "$SHA" ] || {
  echo "verify: $CANDIDATE is not the binary compile.json describes" >&2
  exit 1
}

"$CANDIDATE" --version | grep -qxF "$VERSION" || {
  echo "verify: --version does not report $VERSION" >&2
  exit 1
}
# Network failures are reported by the command and still exit 0.
timeout 120 "$CANDIDATE" update </dev/null > "$WORK/update-smoke.log" 2>&1 || {
  echo "verify: update command failed; inspect $WORK/update-smoke.log" >&2
  exit 1
}
# A small tree: a large one may not finish its scan before the search returns.
FFF_TREE="$WORK/fff-smoke"
rm -rf "$FFF_TREE"
mkdir -p "$FFF_TREE/src"
echo readme > "$FFF_TREE/README.md"
echo code > "$FFF_TREE/src/main.ts"
(cd "$FFF_TREE" && timeout 120 "$CANDIDATE" debug file search readme </dev/null) \
  > "$WORK/fff-smoke.log" 2>&1 || true
grep -qxF README.md "$WORK/fff-smoke.log" || {
  echo "verify: file search did not find README.md; inspect $WORK/fff-smoke.log" >&2
  exit 1
}
python3 "$ROOT/tools/tui_smoke.py" "$CANDIDATE" "$SMOKE_SECONDS" > "$WORK/tui-smoke.log"

python3 - "$DIST/compile.json" "$DIST/build-manifest.json.new" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
doc["smoke"] = {"version": "pass", "update": "pass", "file_search": "pass"}
doc["tui_smoke"] = "pass"
doc["structurally_verified"] = doc["native_assets"].get("result") == "pass"
doc["release_eligible"] = doc["structurally_verified"]
with open(sys.argv[2], "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PY
mv -f "$DIST/build-manifest.json.new" "$DIST/build-manifest.json"
mv -f "$CANDIDATE" "$DIST/opencode"
echo "verify: OK: $DIST/opencode (v$VERSION)"
