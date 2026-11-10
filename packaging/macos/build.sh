#!/bin/sh
# Builds dist/Susurros.app and a disk image of it. Run on an Apple Silicon Mac with uv installed:
#   sh packaging/macos/build.sh
set -eu
cd "$(dirname "$0")/../.."

work=build/macos
mkdir -p "$work"
uv sync --group package
version=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

# The icon is drawn by the app itself, then packed the way macOS wants it.
QT_QPA_PLATFORM=offscreen uv run python -m susurros.cli iconset "$work/Susurros.iconset"
iconutil -c icns "$work/Susurros.iconset" -o "$work/Susurros.icns"

uv run pyinstaller --noconfirm --distpath dist --workpath "$work/work" packaging/macos/Susurros.spec

# No Apple developer certificate: the app is signed "ad hoc", which Apple Silicon requires to run at all.
codesign --force --deep --sign - dist/Susurros.app
codesign --verify --deep --strict dist/Susurros.app

stage=$(mktemp -d)
ditto dist/Susurros.app "$stage/Susurros.app"
ln -s /Applications "$stage/Applications"
image="dist/Susurros-$version-macos-arm64.dmg"
hdiutil create -volname Susurros -srcfolder "$stage" -ov -format UDZO "$image"
echo "Built $image"
