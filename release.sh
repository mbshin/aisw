#!/usr/bin/env bash
# Maintainer only: tag v<version>, push it, and update the formula in the tap repo.
#
#   ./release.sh 1.0.0 [path to a homebrew-tools checkout]
set -euo pipefail

version=${1:?usage: release.sh <version> [tap checkout]}
tap=${2:-$(brew --repository)/Library/Taps/mbshin/homebrew-tools}
repo=$(cd "$(dirname "$0")" && pwd)

[ -z "$(git -C "$repo" status --porcelain)" ] || { echo "Commit first." >&2; exit 1; }
git -C "$repo" tag "v$version"
git -C "$repo" push origin main "v$version"

url=https://github.com/mbshin/clsw/archive/refs/tags/v$version.tar.gz
sha=$(curl -fsSL "$url" | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$tap/Formula"
sed -e "s/@VERSION@/$version/g" -e "s/@SHA256@/$sha/" "$repo/clsw.rb" > "$tap/Formula/clsw.rb"
git -C "$tap" add Formula/clsw.rb
git -C "$tap" commit -qm "clsw $version"
git -C "$tap" push origin HEAD

echo "Released v$version. Users: brew upgrade clsw"
