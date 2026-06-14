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
sudo cp appinstall/usr/share/applications/appinstall.desktop /usr/share/applications/
sudo cp appinstall/usr/share/pixmaps/appinstall.png /usr/share/pixmaps/

# Crear script ejecutable
sudo tee /usr/bin/appinstall > /dev/null << 'EOF'
#!/bin/bash
/usr/bin/python3 "/usr/share/appinstall/start.py"
EOF

# Dar permisos
sudo chmod +x /usr/bin/appinstall

echo "AppInstall instalado correctamente!"
echo "Puedes ejecutarlo con: appinstall"
echo "O buscarlo en el menú de aplicaciones como 'App Install'"