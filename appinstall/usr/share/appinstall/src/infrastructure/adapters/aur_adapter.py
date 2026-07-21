import os
import subprocess
import shutil
import requests
from typing import List, Dict
from src.domain.ports import PackageManager

class AurAdapter(PackageManager):
    def __init__(self):
        self._meta_cache = {}

    def is_available(self) -> bool:
        """Comprueba si el sistema es Arch Linux y tiene pacman."""
        return shutil.which('pacman') is not None

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
            
        results = []
        try:
            # Consultar la API RPC v5 de AUR
            url = f"https://aur.archlinux.org/rpc/v5/search/{query}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                packages = data.get("results", [])
                # Ordenar por popularidad descendente y tomar los primeros 15
                packages = sorted(packages, key=lambda x: x.get("Popularity", 0), reverse=True)
                for pkg in packages[:15]:
                    name = pkg.get("Name")
                    desc = pkg.get("Description", "")
                    version = pkg.get("Version", "")
                    votes = pkg.get("NumVotes", 0)
                    
                    # Guardar en caché para detalles rápidos
                    self._meta_cache[name] = {
                        'developer': pkg.get('Maintainer', ''),
                        'verified': False,
                        'version': version,
                        'description': desc
                    }
                    
                    results.append({
                        'name': name,
                        'display_name': name,
                        'desc': desc or f"Versión {version} ({votes} votos)",
                        'source': 'aur',
                        'icon': 'system-software-install-symbolic'
                    })
        except Exception as e:
            print(f"AUR API search error: {e}")
            
        return results

    def list_installed(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            # Obtener paquetes "extranjeros" (instalados desde AUR u otras fuentes externas)
            output = subprocess.check_output(['pacman', '-Qm'], timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
            return [line.split()[0] for line in output.split('\n') if line.strip()]
        except Exception as e:
            print(f"Error listing installed AUR packages: {e}")
            return []

    def install(self, package: str) -> List[str]:
        # Buscar ayudante de AUR preferido
        if shutil.which('yay'):
            return ['yay', '--sudo', 'pkexec', '-S', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None', package]
        elif shutil.which('paru'):
            return ['paru', '--sudo', 'pkexec', '-S', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None', package]
        else:
            # Fallback nativo: clonar y compilar usando makepkg en el directorio temporal
            # Usamos pkexec para instalar dependencias si makepkg lo pide, pero makepkg debe correr como usuario normal.
            # makepkg se encarga de llamar a sudo pacman automáticamente.
            temp_dir = f"/tmp/appinstall_aur_{package}"
            return [
                'sh', '-c',
                f'rm -rf "{temp_dir}" && ' +
                f'git clone https://aur.archlinux.org/{package}.git "{temp_dir}" && ' +
                f'cd "{temp_dir}" && ' +
                f'makepkg -si --noconfirm --needed && ' +
                f'rm -rf "{temp_dir}"'
            ]
 
    def install_multiple(self, packages: List[str]) -> List[str]:
        if shutil.which('yay'):
            return ['yay', '--sudo', 'pkexec', '-S', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None'] + packages
        elif shutil.which('paru'):
            return ['paru', '--sudo', 'pkexec', '-S', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None'] + packages
        else:
            # Si no hay ayudante de AUR, instalar uno a uno usando el método nativo
            commands = []
            for pkg in packages:
                commands.extend(self.install(pkg))
            return commands

    def install_local(self, file_path: str) -> List[str]:
        return ['pkexec', 'pacman', '-U', '--noconfirm', file_path]

    def uninstall(self, package: str) -> List[str]:
        # Para desinstalar un paquete AUR, usamos el gestor nativo pacman
        return ['pkexec', 'pacman', '-Rns', '--noconfirm', package]

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {
            'name': package_name,
            'version': 'N/A',
            'description': 'Paquete del Arch User Repository (AUR).',
            'size': 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'aur',
            'developer': '',
            'verified': False
        }
        
        cached = self._meta_cache.get(package_name, {})
        if cached:
            info['version'] = cached.get('version', 'N/A')
            info['description'] = cached.get('description', '')
            info['developer'] = cached.get('developer', '')
            info['verified'] = cached.get('verified', False)
        
        try:
            url = f"https://aur.archlinux.org/rpc/v5/info/{package_name}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    pkg = results[0]
                    info['name'] = pkg.get('Name', package_name)
                    info['version'] = pkg.get('Version', 'N/A')
                    info['description'] = pkg.get('Description', '')
                    info['developer'] = pkg.get('Maintainer', '')
                    info['verified'] = False
                    
                    licenses = pkg.get('License', [])
                    if licenses:
                        info['license'] = ", ".join(licenses)
                        
                    url_upstream = pkg.get('URL', '')
                    if url_upstream:
                        info['website'] = url_upstream
        except Exception as e:
            print(f"Error fetching AUR package info: {e}")
            
        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        # AUR local no aplica como archivo directo
        return {
            'name': os.path.basename(file_path),
            'version': 'N/A',
            'description': 'Paquete Arch Linux local.',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB" if os.path.exists(file_path) else 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'aur'
        }

    # Métodos de la interfaz PackageManager que no aplican directamente
    def update_cache(self) -> List[str]:
        if shutil.which('yay'):
            return ['yay', '-Sy']
        elif shutil.which('paru'):
            return ['paru', '-Sy']
        return ['pkexec', 'pacman', '-Sy']
        
    def clean_cache(self) -> List[str]:
        return []
        
    def autoremove(self) -> List[str]:
        return []
        
    def fix_broken(self) -> List[str]:
        return []
        
    def get_cache_directory(self) -> str:
        return "/var/cache/pacman/pkg"
        
    def install_clamav(self) -> List[str]:
        return []
        
    def upgrade_system(self) -> List[str]:
        if shutil.which('yay'):
            return ['yay', '--sudo', 'pkexec', '-Syu', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None']
        elif shutil.which('paru'):
            return ['paru', '--sudo', 'pkexec', '-Syu', '--noconfirm', '--needed', '--answerclean', 'All', '--answerdiff', 'None', '--answeredit', 'None']
        return ['pkexec', 'pacman', '-Syu', '--noconfirm']
