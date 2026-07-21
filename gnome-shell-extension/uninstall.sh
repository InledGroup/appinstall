#!/bin/bash
set -e

EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/appinstall-uninstall@inled.es"

echo "Uninstalling..."

gnome-extensions disable appinstall-uninstall@inled.es 2>/dev/null || true
rm -rf "$EXTENSION_DIR"

echo "Uninstalled!"
