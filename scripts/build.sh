#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT_ELF="${INPUT_ELF:-${1:-$ROOT/work/upstream/opencode}}"
BUN="${BUN:-$ROOT/work/bun-android/bun}"
WORK="$ROOT/work/build"
DIST="$ROOT/dist"
REQUIRE_ALL_BIONIC="${REQUIRE_ALL_BIONIC:-1}"
SMOKE_SECONDS="${SMOKE_SECONDS:-15}"
SKIP_RUN="${SKIP_RUN:-0}"
mkdir -p "$WORK" "$DIST"

exec 9>"$ROOT/.build.lock"
flock -n 9 || { echo "build: another build is running" >&2; exit 1; }
[ -x "$INPUT_ELF" ] || { echo "build: input ELF is missing: $INPUT_ELF" >&2; exit 1; }
[ -x "$BUN" ] || { echo "build: Bionic Bun is missing: $BUN" >&2; exit 1; }

VERSION="${OPENCODE_VERSION:-}"
if [ -z "$VERSION" ] && [ -f "$(dirname "$INPUT_ELF")/version" ]; then
  VERSION="$(tr -d '[:space:]' < "$(dirname "$INPUT_ELF")/version")"
fi
if [ -z "$VERSION" ]; then
  VERSION="$("$INPUT_ELF" --version 2>/dev/null | sed -nE 's/.*v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -n1 || true)"
fi
[ -n "$VERSION" ] || { echo "build: cannot determine OpenCode version" >&2; exit 1; }
GRAPH="$WORK/opencode.graph"
python3 "$ROOT/tools/extract_graph.py" "$INPUT_ELF" "$GRAPH" > "$WORK/extract.json"
python3 "$ROOT/tools/audit_native_assets.py" "$GRAPH" --report "$WORK/native-before.json" >/dev/null

UPDATER_PATCHED="$WORK/opencode.termux-updater.graph"
python3 "$ROOT/tools/patch_updater_graph.py" "$GRAPH" "$UPDATER_PATCHED" \
  --report "$WORK/patch-termux-updater.json" >/dev/null
CURRENT="$UPDATER_PATCHED"
if [ -n "${FFF_SO:-}" ]; then
  FFF_PATCHED="$WORK/opencode.fff-pointers.graph"
  python3 "$ROOT/tools/patch_fff_graph.py" "$CURRENT" "$FFF_PATCHED" \
    --report "$WORK/patch-fff-pointers.json" >/dev/null
  CURRENT="$FFF_PATCHED"
fi

replace_asset() {
  local label="$1" regex="$2" path="$3"
  [ -n "$path" ] || return 0
  [ -f "$path" ] || { echo "build: $label replacement is missing: $path" >&2; exit 1; }
  local next="$WORK/opencode.$label.graph"
  python3 "$ROOT/tools/replace_native_asset.py" "$CURRENT" "$path" "$next" \
    --name-regex "$regex" --report "$WORK/replace-$label.json" >/dev/null
  CURRENT="$next"
}

replace_asset opentui '(?:^|/)libopentui(?:-[^/]*)?\.so$' "${OPENTUI_SO:-}"
replace_asset fff '(?:^|/)libfff_c(?:-[^/]*)?\.so$' "${FFF_SO:-}"
replace_asset watcher '(?:^|/)watcher-[^/]*\.node$' "${WATCHER_NODE:-}"
replace_asset pty-bin '(?:^|/)opencode-pty-[^/]*\.?$' "${OPENCODE_PTY:-}"
replace_asset rust-pty '(?:^|/)librust_pty_arm64-[^/]*\.so$' "${RUST_PTY_SO:-}"

AUDIT_ARGS=()
[ "$REQUIRE_ALL_BIONIC" = 0 ] || AUDIT_ARGS+=(--require-bionic)
python3 "$ROOT/tools/audit_native_assets.py" "$CURRENT" \
  --report "$WORK/native-after.json" "${AUDIT_ARGS[@]}" >/dev/null || {
    echo "build: native asset audit failed; inspect $WORK/native-after.json" >&2
    exit 1
  }

CANDIDATE="$DIST/.opencode.new"
python3 "$ROOT/tools/revive_patch.py" --bun "$BUN" --graph "$CURRENT" --out "$CANDIDATE" \
  > "$WORK/revive.log" 2>&1
chmod 755 "$CANDIDATE"
python3 "$ROOT/tools/verify_graft.py" "$CANDIDATE" "$(stat -c%s "$CURRENT")" \
  > "$WORK/verify-graft.json"
TUI_SMOKE="skipped-cross-build"
if [ "$SKIP_RUN" != 1 ]; then
  "$CANDIDATE" --version | grep -F "$VERSION" >/dev/null
  python3 "$ROOT/tools/tui_smoke.py" "$CANDIDATE" "$SMOKE_SECONDS" > "$WORK/tui-smoke.log"
  TUI_SMOKE="pass"
fi

INPUT_SHA="$(sha256sum "$INPUT_ELF" | cut -d' ' -f1)"
OUTPUT_SHA="$(sha256sum "$CANDIDATE" | cut -d' ' -f1)"
GRAPH_SHA="$(sha256sum "$CURRENT" | cut -d' ' -f1)"
python3 - "$WORK/manifest.json.new" "$VERSION" "$INPUT_SHA" "$OUTPUT_SHA" "$GRAPH_SHA" "$REQUIRE_ALL_BIONIC" "$TUI_SMOKE" \
  "$WORK/extract.json" "$WORK/native-after.json" "$WORK/verify-graft.json" <<'PY'
import json, sys
out, version, input_sha, output_sha, graph_sha, strict, tui_smoke, extract, audit, graft = sys.argv[1:]
def load(path):
    with open(path) as f:
        return json.load(f)
doc = {
    "opencode": version,
    "tag_name": "v" + version,
    "input_sha256": input_sha,
    "output_sha256": output_sha,
    "graph_sha256": graph_sha,
    "extract": load(extract),
    "native_assets": load(audit),
    "graft": load(graft),
    "tui_smoke": tui_smoke,
    "structurally_verified": strict == "1",
    "release_eligible": strict == "1" and tui_smoke == "pass",
}
with open(out, "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PY
mv -f "$WORK/manifest.json.new" "$DIST/build-manifest.json"
mv -f "$CANDIDATE" "$DIST/opencode"
echo "build: OK: $DIST/opencode (v$VERSION)"
