#!/data/data/com.termux/files/usr/bin/bash
# fetch-source.sh [VERSION|latest] [OUT_DIR]
#
# Downloads the OpenCode source of a release tag. The tag is resolved to its
# commit first and the archive is fetched by commit, so a moved tag cannot
# change what a build recorded in source.json.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-latest}"
OUT_DIR="${2:-$ROOT/work/upstream}"
REPO="anomalyco/opencode"
mkdir -p "$OUT_DIR"

if [ "$VERSION" = latest ]; then
  API_ARGS=(-fsSL --retry 5 --retry-all-errors)
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    API_ARGS+=(-H "Authorization: Bearer $GITHUB_TOKEN" -H "X-GitHub-Api-Version: 2022-11-28")
  fi
  VERSION="$(curl "${API_ARGS[@]}" "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')"
fi
VERSION="${VERSION#v}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "fetch-source: invalid OpenCode version: $VERSION" >&2
  exit 1
}

# An annotated tag lists its commit as the peeled refs/tags/vX^{} entry.
REFS="$(git ls-remote "https://github.com/$REPO.git" "refs/tags/v$VERSION" "refs/tags/v$VERSION^{}")"
COMMIT="$(awk '$2 ~ /\^\{\}$/ {print $1}' <<<"$REFS")"
[ -n "$COMMIT" ] || COMMIT="$(awk '{print $1; exit}' <<<"$REFS")"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "fetch-source: tag v$VERSION not found in $REPO" >&2
  exit 1
}

SRC="$OUT_DIR/opencode-src"
if [ -f "$OUT_DIR/source.json" ] && [ -d "$SRC" ] && python3 - "$OUT_DIR/source.json" "$COMMIT" <<'PY'
import json, sys
raise SystemExit(json.load(open(sys.argv[1])).get("commit") != sys.argv[2])
PY
then
  printf '%s\n' "$SRC"
  exit 0
fi

URL="https://codeload.github.com/$REPO/tar.gz/$COMMIT"
ARCHIVE="$OUT_DIR/opencode-$VERSION.tar.gz"
curl -fL --show-error --retry 5 --retry-all-errors -o "$ARCHIVE.new" "$URL"
mv -f "$ARCHIVE.new" "$ARCHIVE"
rm -rf "$SRC" "$SRC.new"
mkdir -p "$SRC.new"
tar -xzf "$ARCHIVE" -C "$SRC.new" --strip-components=1
[ -f "$SRC.new/packages/opencode/script/build.ts" ] || {
  echo "fetch-source: archive has no packages/opencode/script/build.ts" >&2
  exit 1
}
mv "$SRC.new" "$SRC"
python3 - "$OUT_DIR/source.json" "$VERSION" "$COMMIT" "$URL" "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" <<'PY'
import json, sys
out, version, commit, url, sha = sys.argv[1:]
with open(out, "w") as f:
    json.dump({"version": version, "tag": "v" + version, "commit": commit,
               "url": url, "archive_sha256": sha}, f, indent=2)
    f.write("\n")
PY
printf '%s\n' "$SRC"
