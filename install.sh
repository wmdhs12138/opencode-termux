#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPOSITORY="${OPENCODE_TERMUX_REPO:-wmdhs12138/opencode-termux}"
REQUESTED_VERSION="${VERSION:-latest}"
PREFIX_PATH="${PREFIX:-/data/data/com.termux/files/usr}"

die() {
  printf 'opencode-termux: %s\n' "$*" >&2
  exit 1
}

[ "$(uname -m)" = "aarch64" ] || die "only Android AArch64 is supported"
[ -d "$PREFIX_PATH/bin" ] || die "run this installer inside Termux"
command -v curl >/dev/null || die "curl is required (pkg install curl)"

if [ "$REQUESTED_VERSION" = "latest" ]; then
  release_url="$(curl -fsSL --retry 3 -o /dev/null -w '%{url_effective}' \
    "https://github.com/$REPOSITORY/releases/latest")"
  tag="${release_url##*/}"
else
  tag="v${REQUESTED_VERSION#v}"
fi
version="${tag#v}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
  die "could not resolve a valid release version"

api_level="$(getprop ro.build.version.sdk 2>/dev/null || true)"
if [[ "$api_level" =~ ^[0-9]+$ ]] && [ "$api_level" -lt 28 ]; then
  die "Android API 28 or newer is required (device API: $api_level)"
fi

command -v unzip >/dev/null || {
  printf 'Installing the unzip dependency...\n'
  pkg install -y unzip
}

package="opencode-termux-v${version}-android-aarch64"
download="https://github.com/$REPOSITORY/releases/download/$tag"
stage="$(mktemp -d "${TMPDIR:-$PREFIX_PATH/tmp}/opencode-termux.XXXXXX")"
trap 'rm -rf "$stage"' EXIT

printf 'Downloading OpenCode %s for Termux...\n' "$version"
curl -fL --retry 3 --progress-bar -o "$stage/$package.zip" \
  "$download/$package.zip"
curl -fsSL --retry 3 -o "$stage/$package.zip.sha256" \
  "$download/$package.zip.sha256"

(
  cd "$stage"
  sha256sum -c "$package.zip.sha256"
  unzip -q "$package.zip"
)

install -m 755 "$stage/$package/opencode" "$PREFIX_PATH/bin/opencode"
printf 'Installed: %s\n' "$PREFIX_PATH/bin/opencode"
"$PREFIX_PATH/bin/opencode" --version
