import os
import subprocess
import shutil
import requests
from typing import List, Dict
from src.domain.ports import PackageManager
from src.utils.system import get_cached_icon

class FlatpakAdapter(PackageManager):
    def __init__(self):
        self._meta_cache = {}

    def is_available(self) -> bool:
        """Comprueba si flatpak está instalado en el sistema."""
        return shutil.which('flatpak') is not None

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
            
        results = []
        # Intentar buscar a través de la API v2 de Flathub
        try:
            url = "https://flathub.org/api/v2/search"
            payload = {"query": query}
            headers = {"User-Agent": "AppInstall/1.0"}
            r = requests.post(url, json=payload, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", [])
                for hit in hits[:15]:
                    app_id = hit.get("app_id")
                    name = hit.get("name", app_id)
                    summary = hit.get("summary", "")
                    icon_url = hit.get("icon", "")
                    developer = hit.get("developer_name", "")
                    verified = hit.get("verification_verified", False)
                    
                    # Guardar en caché para enriquecer los detalles más tarde
                    self._meta_cache[app_id] = {
                        'developer': developer,
                        'verified': verified
                    }
                    
                    # Descargar y cachear icono en el hilo de fondo
                    cached_icon = ""
                    if icon_url:
                        try:
                            cached_icon = get_cached_icon(icon_url, app_id)
                        except Exception as e:
                            print(f"Error caching Flatpak icon for {app_id}: {e}")
                            
                    results.append({
                        'name': app_id,
                        'display_name': name,
                        'desc': summary,
                        'source': 'flatpak',
                        'icon': cached_icon if cached_icon else 'system-software-install-symbolic'
                    })
                return results
        except Exception as e:
            print(f"Flathub API search error, falling back to CLI: {e}")

        # Fallback a la interfaz de línea de comandos de flatpak
        try:
            cmd = ['flatpak', 'search', '--columns=application,name,description', query]
            output = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
            for line in output.split('\n')[1:]: # Omitir cabecera
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        app_id = parts[0].strip()
                        name = parts[1].strip()
                        desc = parts[2].strip()
                        results.append({
                            'name': app_id,
                            'display_name': name,
                            'desc': desc,
                            'source': 'flatpak',
                            'icon': 'system-software-install-symbolic'
                        })
        except Exception as e:
            print(f"Flatpak CLI search error: {e}")
            
        return results

    def get_popular(self, limit=12) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
        results = []
        try:
            url = "https://flathub.org/api/v2/collection/popular"
            headers = {"User-Agent": "AppInstall/1.0"}
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", [])
                for hit in hits[:limit]:
                    app_id = hit.get("app_id")
                    name = hit.get("name", app_id)
                    summary = hit.get("summary", "")
                    icon_url = hit.get("icon", "")
                    developer = hit.get("developer_name", "")
                    verified = hit.get("verification_verified", False)
                    
                    self._meta_cache[app_id] = {
                        'developer': developer,
                        'verified': verified
                    }
                    
                    cached_icon = ""
                    if icon_url:
                        try:
                            cached_icon = get_cached_icon(icon_url, app_id)
                        except Exception as e:
                            print(f"Error caching Flatpak icon for {app_id}: {e}")
                            
                    results.append({
                        'name': app_id,
                        'display_name': name,
                        'desc': summary,
                        'source': 'flatpak',
                        'icon': cached_icon if cached_icon else 'system-software-install-symbolic'
                    })
        except Exception as e:
            print(f"Flathub API popular error: {e}")
        return results

    def get_trending(self, limit=12) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
        results = []
        try:
            url = "https://flathub.org/api/v2/collection/trending"
            headers = {"User-Agent": "AppInstall/1.0"}
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", [])
                for hit in hits[:limit]:
                    app_id = hit.get("app_id")
                    name = hit.get("name", app_id)
                    summary = hit.get("summary", "")
                    icon_url = hit.get("icon", "")
                    developer = hit.get("developer_name", "")
                    verified = hit.get("verification_verified", False)
                    
                    self._meta_cache[app_id] = {
                        'developer': developer,
                        'verified': verified
                    }
                    
                    cached_icon = ""
                    if icon_url:
                        try:
                            cached_icon = get_cached_icon(icon_url, app_id)
                        except Exception as e:
                            print(f"Error caching Flatpak icon for {app_id}: {e}")
                            
                    results.append({
                        'name': app_id,
                        'display_name': name,
                        'desc': summary,
                        'source': 'flatpak',
                        'icon': cached_icon if cached_icon else 'system-software-install-symbolic'
                    })
        except Exception as e:
            print(f"Flathub API trending error: {e}")
        return results

    def list_installed(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            # Lista los IDs de las aplicaciones flatpak instaladas
            output = subprocess.check_output(['flatpak', 'list', '--columns=application'], timeout=10).decode('utf-8')
            return [line.strip() for line in output.split('\n') if line.strip() and not line.startswith('Application ID')]
        except Exception as e:
            print(f"Error listing installed flatpaks: {e}")
            return []

    def install(self, package: str) -> List[str]:
        # Usamos pkexec para instalar de forma global, o flatpak sin pkexec si es de usuario
        return ['pkexec', 'flatpak', 'install', '-y', 'flathub', package]

    def install_multiple(self, packages: List[str]) -> List[str]:
        return ['pkexec', 'flatpak', 'install', '-y', 'flathub'] + packages

    def install_local(self, file_path: str) -> List[str]:
        # Para archivos .flatpakref o .flatpak
        return ['pkexec', 'flatpak', 'install', '-y', file_path]

    def uninstall(self, package: str) -> List[str]:
        return ['pkexec', 'flatpak', 'uninstall', '-y', package]

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {
            'name': package_name,
            'app_id': package_name,   # reverse-DNS ID used for flatpak CLI checks
            'version': 'N/A',
            'description': 'Aplicación Flatpak de Flathub.',
            'size': 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'flatpak',
            'developer': '',
            'verified': False
        }
        
        # Cargar de la caché en memoria si está disponible
        cached = self._meta_cache.get(package_name, {})
        if cached:
            info['developer'] = cached.get('developer', '')
            info['verified'] = cached.get('verified', False)
        
        # 1. Intentar obtener información de Appstream vía Flathub API
        try:
            url = f"https://flathub.org/api/v2/appstream/{package_name}"
            r = requests.get(url, headers={"User-Agent": "AppInstall/1.0"}, timeout=4)
            if r.status_code == 200:
                data = r.json()
                info['name'] = data.get('name', package_name)
                info['description'] = data.get('description', data.get('summary', ''))
                info['license'] = data.get('project_license', '')
                if 'developer_name' in data:
                    info['developer'] = data['developer_name']
                
                # Buscar icono
                icon_url = data.get('icon', '')
                if icon_url:
                    cached_icon = get_cached_icon(icon_url, package_name)
                    if cached_icon:
                        info['icon'] = cached_icon
                        
                # Obtener versión si está disponible
                releases = data.get('releases', [])
                if releases:
                    info['version'] = releases[0].get('version', 'N/A')

                # Obtener screenshots si están disponibles
                screenshots = []
                for shot in data.get('screenshots', []):
                    sizes = shot.get('sizes', [])
                    if sizes:
                        selected_src = sizes[0].get('src', '')
                        for sz in sizes:
                            try:
                                w = int(sz.get('width', 0))
                                if 600 <= w <= 800:
                                    selected_src = sz.get('src')
                                    break
                            except:
                                pass
                        if selected_src:
                            screenshots.append(selected_src)
                
                # Descargar y cachear hasta 3 screenshots en el hilo de fondo
                cached_screenshots = []
                for idx, src in enumerate(screenshots[:3]):
                    try:
                        cached_path = get_cached_icon(src, f"{package_name}_screenshot_{idx}")
                        if cached_path:
                            cached_screenshots.append(cached_path)
                    except Exception as e:
                        print(f"Error caching screenshot {src}: {e}")
                info['cached_screenshots'] = cached_screenshots
        except Exception as e:
            print(f"Error fetching Flathub appstream API for {package_name}: {e}")
            
        # 2. Intentar obtener tamaño desde la API summary
        try:
            url = f"https://flathub.org/api/v2/summary/{package_name}"
            r = requests.get(url, headers={"User-Agent": "AppInstall/1.0"}, timeout=3)
            if r.status_code == 200:
                data = r.json()
                # download_size o installed_size en bytes
                size_bytes = data.get('download_size', 0) or data.get('installed_size', 0)
                if size_bytes:
                    info['size'] = f"{size_bytes / (1024*1024):.1f} MB"
        except Exception as e:
            print(f"Error fetching Flathub summary API for {package_name}: {e}")

        # 3. Fallback a flatpak CLI si ya está instalado o disponible localmente
        if info['version'] == 'N/A' and self.is_available():
            try:
                cmd = ['flatpak', 'info', package_name]
                output = subprocess.check_output(cmd, timeout=5, stderr=subprocess.DEVNULL).decode('utf-8')
                for line in output.split('\n'):
                    if line.startswith('Version:'):
                        info['version'] = line.replace('Version:', '').strip()
                        break
            except:
                pass
                
        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        # Para archivos locales de tipo flatpakref o bundle
        info = {
            'name': os.path.basename(file_path),
            'version': 'N/A',
            'description': 'Archivo de instalación Flatpak',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB" if os.path.exists(file_path) else 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'flatpak'
        }
        return info

    # Métodos de la interfaz PackageManager que no aplican a Flatpak
    def update_cache(self) -> List[str]:
        return ['flatpak', 'update', '--appstream']
        
    def clean_cache(self) -> List[str]:
        return ['flatpak', 'uninstall', '--unused', '-y']
        
    def autoremove(self) -> List[str]:
        return ['flatpak', 'uninstall', '--unused', '-y']
        
    def fix_broken(self) -> List[str]:
        return ['flatpak', 'repair']
        
    def get_cache_directory(self) -> str:
        return "~/.local/share/flatpak"
        
    def install_clamav(self) -> List[str]:
        return []
        
    def upgrade_system(self) -> List[str]:
        return ['flatpak', 'update', '-y']
