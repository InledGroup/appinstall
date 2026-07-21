#!/bin/bash

# Script local para construir el paquete .deb de AppInstall
# Lee la versión de src/utils/constants.py y la incrementa automáticamente

# Asegurar que estamos en el directorio raíz del proyecto
cd "$(dirname "$0")"

CONSTANTS_FILE="src/utils/constants.py"
CONTROL_FILE="appinstall/DEBIAN/control"

# Leer versión actual desde constants.py (fuente única de verdad)
CURRENT_VERSION=$(python3 -c "
import re, sys
with open('$CONSTANTS_FILE') as f:
    m = re.search(r'CURRENT_VERSION\s*=\s*\"([^\"]+)\"', f.read())
    if m:
        print(m.group(1))
    else:
        print('1')
        sys.exit(1)
")

echo "Versión actual en constants.py: $CURRENT_VERSION"

# Auto-incrementar: si es "20" → "20.1", si es "20.1" → "20.2", etc.
if [[ "$CURRENT_VERSION" == *.* ]]; then
    MAJOR="${CURRENT_VERSION%.*}"
    MINOR="${CURRENT_VERSION#*.}"
    NEW_MINOR=$((MINOR + 1))
    NEW_VERSION="${MAJOR}.${NEW_MINOR}"
else
    NEW_VERSION="${CURRENT_VERSION}.1"
fi

echo "Nueva versión: $NEW_VERSION"

# Actualizar constants.py
sed -i "s/CURRENT_VERSION = \"${CURRENT_VERSION}\"/CURRENT_VERSION = \"${NEW_VERSION}\"/" "$CONSTANTS_FILE"

# Actualizar DEBIAN/control
sed -i "s/^Version: .*/Version: ${NEW_VERSION}/" "$CONTROL_FILE"

PACKAGE_NAME=$(grep '^Package:' "$CONTROL_FILE" | cut -d' ' -f2)
ARCH=$(grep '^Architecture:' "$CONTROL_FILE" | cut -d' ' -f2)
DEB_FILE="${PACKAGE_NAME}_${NEW_VERSION}_${ARCH}.deb"

echo "Construyendo $DEB_FILE..."

# Compilar traducciones
if [ -f "compile_locales.py" ]; then
    echo "Compilando traducciones..."
    python3 compile_locales.py
fi

# Sincronizar archivos del código fuente a la estructura del paquete
echo "Sincronizando archivos..."
mkdir -p appinstall/usr/share/appinstall/
cp -r src/ appinstall/usr/share/appinstall/
cp start.py appinstall/usr/share/appinstall/
cp styles.css appinstall/usr/share/appinstall/
cp appimage.png appinstall/usr/share/appinstall/

# Sincronizar archivos de integración del sistema
mkdir -p appinstall/usr/share/applications/
cp es.inled.AppInstall.desktop appinstall/usr/share/applications/

mkdir -p appinstall/usr/share/metainfo/
cp es.inled.AppInstall.metainfo.xml appinstall/usr/share/metainfo/

# Asegurar que los iconos están en las rutas correctas
mkdir -p appinstall/usr/share/icons/hicolor/512x512/apps/
cp es.inled.AppInstall.png appinstall/usr/share/icons/hicolor/512x512/apps/es.inled.AppInstall.png
mkdir -p appinstall/usr/share/pixmaps/
cp es.inled.AppInstall.png appinstall/usr/share/pixmaps/es.inled.AppInstall.png

# Ajustar permisos necesarios para el paquete Debian
echo "Ajustando permisos..."
chmod -R 755 appinstall/usr
chmod 755 appinstall/DEBIAN/postinst
chmod 755 appinstall/usr/bin/appinstall
# Los archivos de control deben tener permisos específicos (644)
chmod 644 appinstall/DEBIAN/control

# Crear symlink para CLI_NAME desde config
CLI_NAME=$(python3 -c "import sys; sys.path.insert(0, 'appinstall/usr/share/appinstall'); from src.config import CLI_NAME; print(CLI_NAME)" 2>/dev/null || echo "appi")
ln -sf /usr/bin/appinstall "appinstall/usr/bin/$CLI_NAME" 2>/dev/null || true

# Construir el paquete
if command -v dpkg-deb >/dev/null; then
    dpkg-deb --root-owner-group --build appinstall "$DEB_FILE"
    echo "¡Hecho! El paquete se ha creado: $DEB_FILE"
else
    echo "Error: dpkg-deb no está instalado. No puedo construir el paquete."
    exit 1
fi
