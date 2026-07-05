import subprocess
import os
from typing import List, Dict
from src.domain.ports import PackageManager

# English: Package manager adapter for Arch Linux using Pacman
# Español: Adaptador del gestor de paquetes para Arch Linux usando Pacman
class PacmanAdapter(PackageManager):
    def search(self, query: str) -> List[Dict[str, str]]:
        # English: Search for packages in repositories using pacman -Ss
        # Español: Buscar paquetes en los repositorios usando pacman -Ss
        results = []
        try:
            output = subprocess.check_output(['pacman', '-Ss', query], timeout=15).decode('utf-8', errors='ignore')
            lines = output.split('\n')
            current_name = None
            for line in lines:
                if not line.strip():
                    continue
                # English: Description lines are indented
                # Español: Las líneas de descripción están indentadas
                if line.startswith('    ') or line.startswith('\t'):
                    if current_name:
                        desc = line.strip()
                        results.append({'name': current_name, 'desc': desc, 'source': 'pacman'})
                        current_name = None
                else:
                    # English: Package line format: repo/package_name version [installed]
                    # Español: Formato de la línea de paquete: repo/nombre_paquete versión [instalado]
                    parts = line.strip().split()
                    if parts and '/' in parts[0]:
                        repo_name = parts[0]
                        current_name = repo_name.split('/', 1)[1]
        except Exception as e:
            print(f"Error in pacman search: {e}")
        return results

    def list_installed(self) -> List[str]:
        # English: List all installed packages using pacman -Qq
        # Español: Listar todos los paquetes instalados usando pacman -Qq
        try:
            output = subprocess.check_output(['pacman', '-Qq'], timeout=15).decode('utf-8')
            return [line.strip() for line in output.split('\n') if line.strip()]
        except Exception as e:
            print(f"Error listing installed packages: {e}")
            return []

    def install(self, package: str) -> List[str]:
        # English: Return command to install a single package
        # Español: Devolver comando para instalar un único paquete
        return ['pkexec', 'pacman', '-S', '--noconfirm', package]

    def install_multiple(self, packages: List[str]) -> List[str]:
        # English: Return command to install multiple packages
        # Español: Devolver comando para instalar varios paquetes
        return ['pkexec', 'pacman', '-S', '--noconfirm'] + packages

    def install_local(self, file_path: str) -> List[str]:
        # English: Return command to install a local package file (.pkg.tar.zst)
        # Español: Devolver comando para instalar un archivo de paquete local (.pkg.tar.zst)
        return ['pkexec', 'pacman', '-U', '--noconfirm', file_path]

    def uninstall(self, package: str) -> List[str]:
        # English: Return command to uninstall a package
        # Español: Devolver comando para desinstalar un paquete
        return ['pkexec', 'pacman', '-R', '--noconfirm', package]

    def update_cache(self) -> List[str]:
        # English: Return command to synchronize database cache
        # Español: Devolver comando para sincronizar la caché de la base de datos
        return ['pkexec', 'pacman', '-Sy']

    def clean_cache(self) -> List[str]:
        # English: Return command to clean pacman cache
        # Español: Devolver comando para limpiar la caché de pacman
        return ['pkexec', 'pacman', '-Sc', '--noconfirm']

    def autoremove(self) -> List[str]:
        # English: Return command to remove orphan packages
        # Español: Devolver comando para eliminar paquetes huérfanos
        return ['pkexec', 'sh', '-c', 'pacman -Qtdq | xargs -r pacman -Rns --noconfirm']

    def fix_broken(self) -> List[str]:
        # English: Pacman doesn't have an exact 'fix' command, synchronize database as fallback
        # Español: Pacman no tiene un comando de reparación exacto, sincroniza la base de datos por defecto
        return ['pkexec', 'pacman', '-Sy']

    def get_cache_directory(self) -> str:
        # English: Return standard pacman cache directory
        # Español: Devolver el directorio estándar de caché de pacman
        return "/var/cache/pacman/pkg"

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        # English: Get metadata from local package file (.pkg.tar.zst)
        # Español: Obtener metadatos de un archivo de paquete local (.pkg.tar.zst)
        info = {'name': '', 'version': '', 'description': '', 'size': '', 'icon': ''}
        try:
            env = os.environ.copy()
            env['LANG'] = 'C'
            # English: Extract metadata using pacman -Qip
            # Español: Extraer metadatos usando pacman -Qip
            cmd = ['pacman', '-Qip', file_path]
            output = subprocess.check_output(cmd, env=env, timeout=10).decode('utf-8', errors='ignore')
            info = self._parse_pacman_info(output)
            
            # English: Extract icon from package archive if present
            # Español: Extraer el icono del archivo del paquete si está presente
            try:
                # English: List files inside the package
                # Español: Listar los archivos dentro del paquete
                files = subprocess.check_output(['tar', '-tf', file_path], timeout=10).decode('utf-8', errors='ignore').split('\n')
                icon_path = None
                
                # English: Priority: hicolor/apps -> pixmaps
                # Español: Prioridad: hicolor/apps -> pixmaps
                for f in files:
                    f = f.strip()
                    if 'usr/share/icons/hicolor/' in f and '/apps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                        icon_path = f
                        break
                if not icon_path:
                    for f in files:
                        f = f.strip()
                        if 'usr/share/pixmaps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                            icon_path = f
                            break
                
                if icon_path:
                    import tempfile
                    temp_dir = os.path.join(tempfile.gettempdir(), 'appinstall_icons')
                    os.makedirs(temp_dir, exist_ok=True)
                    out_path = os.path.join(temp_dir, os.path.basename(icon_path))
                    
                    # English: Extract single file using tar stdout redirection
                    # Español: Extraer un solo archivo usando la redirección de salida de tar
                    subprocess.run(f"tar -xf {file_path} -O {icon_path} > {out_path}", shell=True, timeout=5)
                    info['icon'] = out_path
            except Exception as e:
                print(f"Error extracting icon from pacman file: {e}")
        except Exception as e:
            print(f"Error reading pacman file info: {e}")
        return info

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        # English: Get metadata from repository package using pacman -Si
        # Español: Obtener metadatos del paquete en los repositorios usando pacman -Si
        info = {'name': package_name, 'version': '', 'description': '', 'size': '', 'icon': ''}
        try:
            env = os.environ.copy()
            env['LANG'] = 'C'
            output = subprocess.check_output(['pacman', '-Si', package_name], env=env, timeout=10).decode('utf-8', errors='ignore')
            info = self._parse_pacman_info(output)
            
            # English: Try to resolve icon from system theme using package name
            # Español: Intentar resolver el icono del tema del sistema usando el nombre del paquete
            try:
                from gi.repository import Gtk, Gdk
                theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                icon_names = [package_name, package_name.split('-')[0]]
                for name in icon_names:
                    if theme.has_icon(name):
                        info['icon'] = name
                        break
            except:
                pass
        except Exception as e:
            print(f"Error reading package info: {e}")
        return info

    def install_clamav(self) -> List[str]:
        # English: Return command to install ClamAV antivirus package
        # Español: Devolver comando para instalar el paquete del antivirus ClamAV
        return ['pkexec', 'pacman', '-S', '--noconfirm', 'clamav']

    def upgrade_system(self) -> List[str]:
        # English: Return command to synchronize database and upgrade all system packages
        # Español: Devolver comando para sincronizar base de datos y actualizar todos los paquetes del sistema
        return ['pkexec', 'pacman', '-Syu', '--noconfirm']

    def _parse_pacman_info(self, output: str) -> Dict[str, str]:
        # English: Helper function to parse pacman info outputs (both -Qip and -Si)
        # Español: Función auxiliar para parsear las salidas de información de pacman (tanto -Qip como -Si)
        info = {'name': '', 'version': '', 'description': '', 'size': '', 'icon': ''}
        for line in output.split('\n'):
            if ':' not in line:
                continue
            parts = line.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip()
            
            if key == 'Name':
                info['name'] = value
            elif key == 'Version':
                info['version'] = value
            elif key == 'Description':
                info['description'] = value
            elif key == 'Installed Size':
                info['size'] = value
        return info
