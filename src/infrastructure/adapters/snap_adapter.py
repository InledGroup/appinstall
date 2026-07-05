import os
import subprocess
import shutil
import re
import requests
from typing import List, Dict
from src.domain.ports import PackageManager
from src.utils.system import get_cached_icon

class SnapAdapter(PackageManager):
    def __init__(self):
        self._meta_cache = {}

    def is_available(self) -> bool:
        """Comprueba si snapd está disponible."""
        return shutil.which('snap') is not None

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
            
        results = []
        try:
            # Ejecutar snap find para obtener los resultados iniciales
            cmd = ['snap', 'find', query]
            output = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
            lines = output.split('\n')
            
            # La primera línea es la cabecera (Name, Version, Publisher, Notes, Summary)
            if len(lines) <= 1:
                return []
                
            for line in lines[1:]:
                if not line.strip():
                    continue
                # Separar por dos o más espacios
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 2:
                    name = parts[0].strip()
                    version = parts[1].strip()
                    publisher = parts[2].strip() if len(parts) > 2 else ""
                    notes = parts[3].strip() if len(parts) > 3 else ""
                    summary = parts[4].strip() if len(parts) > 4 else (parts[3].strip() if len(parts) > 3 and notes != "-" else "")
                    
                    results.append({
                        'name': name,
                        'display_name': name,
                        'desc': summary or f"Publicado por {publisher}",
                        'source': 'snap',
                        'icon': 'system-software-install-symbolic',
                        'classic': 'classic' in notes.lower()
                    })
            
            # Enriquecer los primeros 5 resultados con iconos usando la API de Snapcraft
            for res in results[:5]:
                snap_name = res['name']
                try:
                    url = f"https://api.snapcraft.io/api/v1/snaps/details/{snap_name}"
                    headers = {
                        "X-Ubuntu-Series": "16",
                        "User-Agent": "AppInstall/1.0"
                    }
                    r = requests.get(url, headers=headers, timeout=2)
                    if r.status_code == 200:
                        data = r.json()
                        icon_url = data.get("icon_url", "")
                        cached_icon = ""
                        if icon_url:
                            cached_icon = get_cached_icon(icon_url, snap_name)
                            if cached_icon:
                                res['icon'] = cached_icon
                        
                        # Si hay un título más descriptivo en la API, usarlo
                        title = data.get("title", "")
                        if title:
                            res['display_name'] = title
                            
                        # Guardar en caché para detalles rápidos
                        self._meta_cache[snap_name] = {
                            'developer': data.get('developer_name', ''),
                            'verified': data.get('developer_validation', '') == 'verified',
                            'version': data.get('version', 'N/A'),
                            'description': data.get('description', data.get('summary', '')),
                            'license': data.get('license', ''),
                            'size': f"{data.get('binary_filesize', 0) / (1024*1024):.1f} MB" if data.get('binary_filesize', 0) else 'N/A',
                            'icon': cached_icon if cached_icon else 'system-software-install-symbolic',
                            'title': title if title else snap_name
                        }
                except Exception as e:
                    print(f"Error enriching Snap details for {snap_name}: {e}")
                    
        except Exception as e:
            print(f"Snap search error: {e}")
            
        return results

    def list_installed(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            output = subprocess.check_output(['snap', 'list'], timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
            lines = output.split('\n')
            if len(lines) <= 1:
                return []
            installed = []
            for line in lines[1:]:
                if line.strip():
                    parts = line.split()
                    if parts:
                        installed.append(parts[0])
            return installed
        except Exception as e:
            print(f"Error listing installed snaps: {e}")
            return []

    def install(self, package: str) -> List[str]:
        # Si requiere modo classic, añadir la opción
        cmd = ['pkexec', 'snap', 'install', package]
        if self._is_classic_required_from_store(package):
            cmd.append('--classic')
        return cmd

    def install_multiple(self, packages: List[str]) -> List[str]:
        return ['pkexec', 'snap', 'install'] + packages

    def install_local(self, file_path: str) -> List[str]:
        # Instalación de archivo snap local
        return ['pkexec', 'snap', 'install', '--dangerous', file_path]

    def uninstall(self, package: str) -> List[str]:
        return ['pkexec', 'snap', 'remove', package]

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {
            'name': package_name,
            'version': 'N/A',
            'description': 'Aplicación Snap del Snap Store.',
            'size': 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'snap',
            'developer': '',
            'verified': False
        }
        
        cached = self._meta_cache.get(package_name, {})
        if cached:
            info['name'] = cached.get('title', package_name)
            info['version'] = cached.get('version', 'N/A')
            info['description'] = cached.get('description', '')
            info['license'] = cached.get('license', '')
            info['size'] = cached.get('size', 'N/A')
            info['icon'] = cached.get('icon', 'system-software-install-symbolic')
            info['developer'] = cached.get('developer', '')
            info['verified'] = cached.get('verified', False)
            return info
            
        try:
            url = f"https://api.snapcraft.io/api/v1/snaps/details/{package_name}"
            headers = {
                "X-Ubuntu-Series": "16",
                "User-Agent": "AppInstall/1.0"
            }
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                data = r.json()
                info['name'] = data.get('title', data.get('package_name', package_name))
                info['version'] = data.get('version', 'N/A')
                info['description'] = data.get('description', data.get('summary', ''))
                info['license'] = data.get('license', '')
                info['developer'] = data.get('developer_name', '')
                info['verified'] = data.get('developer_validation', '') == 'verified'
                
                size_bytes = data.get('binary_filesize', 0)
                if size_bytes:
                    info['size'] = f"{size_bytes / (1024*1024):.1f} MB"
                    
                icon_url = data.get('icon_url', '')
                if icon_url:
                    cached = get_cached_icon(icon_url, package_name)
                    if cached:
                        info['icon'] = cached
        except Exception as e:
            print(f"Error fetching snap details from API: {e}")
            
        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        info = {
            'name': os.path.basename(file_path),
            'version': 'N/A',
            'description': 'Paquete Snap local.',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB" if os.path.exists(file_path) else 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'snap'
        }
        return info

    def _is_classic_required_from_store(self, package_name: str) -> bool:
        """Consulta la API de Snapcraft para saber si requiere confinamiento clásico."""
        try:
            url = f"https://api.snapcraft.io/api/v1/snaps/details/{package_name}"
            headers = {
                "X-Ubuntu-Series": "16",
                "User-Agent": "AppInstall/1.0"
            }
            r = requests.get(url, headers=headers, timeout=2)
            if r.status_code == 200:
                data = r.json()
                return data.get('confinement', '') == 'classic'
        except:
            pass
        return False

    # Métodos de la interfaz PackageManager que no aplican a Snap
    def update_cache(self) -> List[str]:
        return ['snap', 'refresh', '--list']
        
    def clean_cache(self) -> List[str]:
        return []
        
    def autoremove(self) -> List[str]:
        return []
        
    def fix_broken(self) -> List[str]:
        return []
        
    def get_cache_directory(self) -> str:
        return "/var/lib/snapd/cache"
        
    def install_clamav(self) -> List[str]:
        return []
        
    def upgrade_system(self) -> List[str]:
        return ['pkexec', 'snap', 'refresh']
