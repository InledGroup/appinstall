#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UUID="appinstall-uninstall@inled.es"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"

echo "Packaging extension..."
"$SCRIPT_DIR/pack.sh"

ZIP="$SCRIPT_DIR/${UUID}.shell-extension.zip"
if [ ! -f "$ZIP" ]; then
    echo "Error: zip not found at $ZIP"
    exit 1
fi

echo "Installing from zip..."
mkdir -p "$EXTENSION_DIR"
unzip -o "$ZIP" -d "$EXTENSION_DIR"

echo ""
echo "Installed -> $EXTENSION_DIR"
echo ""
echo "Activate:"
echo "  gnome-extensions enable $UUID"
echo ""
echo "Restart GNOME Shell:"
echo "  - X11:    Alt+F2 → r → Enter"
echo "  - Wayland: close session or run nested using mutter devkit"
echo ""
echo "Preferences:"
echo "  gnome-extensions prefs $UUID"
