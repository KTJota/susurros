#!/bin/sh
# Publishes the two releases of a version from a finished "Build" run on GitHub:
#   sh scripts/publish-release.sh RUN_ID
# The version is the one in pyproject.toml at the commit the run built. Needs the gh CLI.
set -eu
run=${1:?usage: publish-release.sh RUN_ID}
cd "$(dirname "$0")/.."

commit=$(gh run view "$run" --json headSha --jq .headSha)
folder=$(mktemp -d)
gh run download "$run" --name windows --name macos --dir "$folder"
zip=$(ls "$folder"/windows/Susurros-*-windows.zip)
image=$(ls "$folder"/macos/Susurros-*-macos-arm64.dmg)
version=$(basename "$zip" -windows.zip)
version=${version#Susurros-}

gh release create "v$version-windows" "$zip" --target "$commit" \
    --title "Susurros $version for Windows" --notes-file packaging/release-notes/windows.md
gh release create "v$version-macos" "$image" --target "$commit" \
    --title "Susurros $version for macOS" --notes-file packaging/release-notes/macos.md
