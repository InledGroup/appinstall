#!/bin/bash

# Script de instalación manual de AppInstall

echo "Instalando AppInstall manualmente..."

# Crear directorios
sudo mkdir -p /usr/share/appinstall
sudo mkdir -p /usr/share/applications
sudo mkdir -p /usr/share/pixmaps

# Copiar archivos
sudo cp start.py /usr/share/appinstall/
sudo cp styles.css /usr/share/appinstall/
sudo cp appimage.png /usr/share/appinstall/
sudo cp -r src /usr/share/appinstall/
sudo cp -r locale /usr/share/appinstall/ 2>/dev/null || true
sudo cp appinstall/usr/share/applications/appinstall.desktop /usr/share/applications/
sudo cp appinstall/usr/share/pixmaps/appinstall.png /usr/share/pixmaps/

# Crear script ejecutable
sudo tee /usr/bin/appinstall > /dev/null << 'EOF'
#!/bin/bash
/usr/bin/python3 "/usr/share/appinstall/start.py" "$@"
EOF

# Leer nombre CLI del config y crear symlink
CLI_NAME=$(python3 -c "import sys; sys.path.insert(0, '/usr/share/appinstall'); from src.config import CLI_NAME; print(CLI_NAME)")
sudo ln -sf /usr/bin/appinstall "/usr/bin/$CLI_NAME"

# Dar permisos
sudo chmod +x /usr/bin/appinstall

echo "AppInstall instalado correctamente!"
echo "CLI disponible como: $CLI_NAME"
echo "También puedes usar: appinstall"
echo "O buscarlo en el menú de aplicaciones como 'App Install'"