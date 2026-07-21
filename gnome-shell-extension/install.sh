#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/appinstall-uninstall@inled.es"

echo "Instalando extensión AppInstall Uninstall..."

mkdir -p "$EXTENSION_DIR"
cp "$SCRIPT_DIR/metadata.json" "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/extension.js" "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/prefs.js" "$EXTENSION_DIR/"
cp -r "$SCRIPT_DIR/schemas" "$EXTENSION_DIR/"

echo "Extensión instalada en: $EXTENSION_DIR"
echo ""
echo "Para activarla:"
echo "  gnome-extensions enable appinstall-uninstall@inled.es"
echo ""
echo "Para que los cambios surtan effect, reinicia GNOME Shell:"
echo "  - En X11: Alt+F2, escribe 'r', Enter"
echo "  - En Wayland: cierra sesión y vuelve a entrar"
echo ""
echo "Configuración:"
echo "  gnome-extensions prefs appinstall-uninstall@inled.es"
