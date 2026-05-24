#!/bin/bash

# Script local para construir el paquete .deb de AppInstall

# Asegurar que estamos en el directorio raíz del proyecto
cd "$(dirname "$0")"

# Nombre del paquete y versión (extraídos del archivo control)
PACKAGE_NAME=$(grep '^Package:' appinstall/DEBIAN/control | cut -d' ' -f2)
VERSION=$(grep '^Version:' appinstall/DEBIAN/control | cut -d' ' -f2)
ARCH=$(grep '^Architecture:' appinstall/DEBIAN/control | cut -d' ' -f2)

DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"

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
# Los archivos de control deben tener permisos específicos (644)
chmod 644 appinstall/DEBIAN/control

# Construir el paquete
if command -v dpkg-deb >/dev/null; then
    dpkg-deb --root-owner-group --build appinstall "$DEB_FILE"
    echo "¡Hecho! El paquete se ha creado: $DEB_FILE"
else
    echo "Error: dpkg-deb no está instalado. No puedo construir el paquete."
    exit 1
fi
