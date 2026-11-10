#!/bin/sh
# Makes public the draft releases that a "Build" run with "release" ticked has prepared:
#   sh scripts/publish-release.sh VERSION      (for example: 0.3.0)
# Needs the gh CLI. Look at the drafts on GitHub first.
set -eu
version=${1:?usage: publish-release.sh VERSION}
for system in linux macos windows; do
    gh release edit "v$version-$system" --draft=false --latest=false
done
gh release edit "v$version-windows" --latest
