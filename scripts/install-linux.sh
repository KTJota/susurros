#!/usr/bin/env bash
# Installs Susurros on Ubuntu or Debian. Either from a copy of the project:
#   bash scripts/install-linux.sh
# or straight from the internet (it downloads the latest Linux release):
#   curl -fsSL https://raw.githubusercontent.com/KTJota/susurros/main/scripts/install-linux.sh | bash
# It asks for your password once, to install system packages and to let your user read the
# keyboard and press the paste shortcut (the `input` group).
set -euo pipefail

repo="KTJota/susurros"
base="${XDG_DATA_HOME:-$HOME/.local/share}/susurros"
venv="$base/venv"
mkdir -p "$base"

echo "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl ca-certificates libportaudio2 pulseaudio-utils \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 \
    libxcb-xkb1 libxkbcommon-x11-0 libegl1 libgl1 libfontconfig1 libdbus-1-3

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (it downloads Python and the libraries Susurros needs)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# The project: the copy this script lives in, or the latest Linux release.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$script_dir" ] && [ -f "$script_dir/../pyproject.toml" ]; then
    project="$(cd "$script_dir/.." && pwd)"
else
    echo "Downloading Susurros..."
    url=$(curl -fsSL "https://api.github.com/repos/$repo/releases?per_page=30" \
        | grep -o 'https://[^"]*-linux\.tar\.gz' | head -n 1)
    [ -n "$url" ] || { echo "No Linux release of Susurros was found." >&2; exit 1; }
    source_dir="$base/source"
    mkdir -p "$source_dir.new"
    curl -fsSL "$url" | tar -xz -C "$source_dir.new" --strip-components=1
    if [ -d "$source_dir" ]; then mv "$source_dir" "$source_dir.old.$$"; fi
    mv "$source_dir.new" "$source_dir"
    project="$source_dir"
fi

# If the app is open, close it before updating.
pkill -f "$venv/bin/python.* -m susurros" 2>/dev/null || true

extra=()
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA card found: adding the GPU libraries (a large download)."
    extra=(--extra gpu)
fi
echo "Installing Susurros..."
UV_PROJECT_ENVIRONMENT="$venv" UV_LINK_MODE=copy \
    uv sync --project "$project" --no-dev --no-editable --reinstall-package susurros "${extra[@]}"

# Reading the keyboard and pressing the paste shortcut go through the kernel's input devices.
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
    sudo usermod -aG input "$USER"
    relogin=1
fi
rule='KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"'
if [ "$(cat /etc/udev/rules.d/70-susurros-uinput.rules 2>/dev/null)" != "$rule" ]; then
    echo "$rule" | sudo tee /etc/udev/rules.d/70-susurros-uinput.rules >/dev/null
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo udevadm trigger --name-match=uinput 2>/dev/null || true
fi

# Menu entry and icon.
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$icons" "$apps" "$base/icon"
QT_QPA_PLATFORM=offscreen "$venv/bin/python" -m susurros.cli iconset "$base/icon"
cp "$base/icon/icon_256x256.png" "$icons/susurros.png"
cat > "$apps/susurros.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Susurros
Comment=Voice dictation
Exec=$venv/bin/python -m susurros
Icon=susurros
Terminal=false
Categories=Utility;
ENTRY
update-desktop-database "$apps" 2>/dev/null || true

echo
echo "Susurros is installed. Find it in your applications menu."
if [ "${relogin:-0}" = 1 ]; then
    echo "Log out and back in first: that is when the keyboard permission takes effect."
fi
