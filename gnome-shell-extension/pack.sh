#!/bin/bash

# Script to package the AppInstall Uninstall GNOME Shell extension
# Produces a .shell-extension.zip ready for manual install or extensions.gnome.org

UUID="appinstall-uninstall@inled.es"
EXTDIR="$(dirname "$0")"

echo "Compiling schemas..."
glib-compile-schemas "$EXTDIR/schemas/"

echo "Packaging $UUID..."
gnome-extensions pack \
    --extra-source=extension.js \
    --extra-source=prefs.js \
    --schema=schemas/org.gnome.shell.extensions.appinstall-uninstall.gschema.xml \
    --force

echo ""
echo "Done: ${UUID}.shell-extension.zip"
