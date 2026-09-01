import os
import subprocess
import tempfile
import re
from typing import Dict
from src.domain.ports import PackageManager
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter
from src.infrastructure.adapters.pulsar_store_adapter import PulsarStoreAdapter

class PackageInfoService:
    def __init__(self, package_manager: PackageManager):
        self.package_manager = package_manager
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()
        self.pulsar_adapter = PulsarStoreAdapter()

    def get_info(self, identifier: str, is_local: bool = True) -> Dict[str, str]:
        if not identifier:
            return {}

        if is_local:
            if not os.path.exists(identifier):
                return {}
            ext = os.path.splitext(identifier)[1].lower()
            # English: Check for supported system packages (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz)
            # Español: Comprobar si son paquetes de sistema compatibles (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz)
            is_local_pkg = (
                ext in ('.deb', '.rpm') or
                identifier.lower().endswith('.pkg.tar.zst') or
                identifier.lower().endswith('.pkg.tar.xz')
            )
            if is_local_pkg:
                return self.package_manager.get_local_file_info(identifier)
            elif ext == '.appimage':
                return self._get_appimage_info(identifier)
        else:
            # Repository package
            if identifier.startswith('flatpak:'):
                pkg_name = identifier.replace('flatpak:', '', 1)
                return self.flatpak_adapter.get_package_info(pkg_name)
            elif identifier.startswith('snap:'):
                pkg_name = identifier.replace('snap:', '', 1)
                return self.snap_adapter.get_package_info(pkg_name)
            elif identifier.startswith('aur:'):
                pkg_name = identifier.replace('aur:', '', 1)
                return self.aur_adapter.get_package_info(pkg_name)
            elif identifier.startswith('brew:'):
                pkg_name = identifier.replace('brew:', '', 1)
                return {
                    'name': pkg_name,
                    'version': 'N/A',
                    'description': 'Fórmula de Homebrew',
                    'size': 'N/A',
                    'icon': 'system-software-install-symbolic',
                    'source': 'brew'
                }
            elif identifier.startswith('pulsar:'):
                pkg_name = identifier.replace('pulsar:', '', 1)
                return self.pulsar_adapter.get_package_info(pkg_name)
            return self.package_manager.get_package_info(identifier)
        
        return {}

    def _get_appimage_info(self, file_path: str) -> Dict[str, str]:
        info = {
            'name': os.path.basename(file_path).replace('.AppImage', '').replace('.appimage', ''),
            'version': 'N/A',
            'description': 'Aplicación en formato AppImage',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB",
            'icon': ''
        }
        
        temp_dir = None
        try:
            # Try to extract icon and desktop file
            temp_dir = tempfile.mkdtemp(prefix='appinstall_extract_')
            
            # For now, let's try a quick extraction of common metadata files
            if subprocess.run(['which', 'unsquashfs'], capture_output=True).returncode == 0:
                # Extracting only needed files to minimize time and space
                subprocess.run(['unsquashfs', '-d', temp_dir, '-f', '-n', '-i', file_path, '.DirIcon'], 
                               capture_output=True, timeout=5)
                extracted_icon = os.path.join(temp_dir, '.DirIcon')
                if os.path.exists(extracted_icon):
                    import shutil
                    final_icon_dir = os.path.join(tempfile.gettempdir(), 'appinstall_icons')
                    os.makedirs(final_icon_dir, exist_ok=True)
                    final_icon = os.path.join(final_icon_dir, f"{info['name']}.png")
                    shutil.copy(extracted_icon, final_icon)
                    info['icon'] = final_icon
                
                # Try to find a desktop file for better name/description
                subprocess.run(['unsquashfs', '-d', temp_dir, '-f', '-n', '-i', file_path, '*.desktop'], 
                               capture_output=True, timeout=5)
                for f in os.listdir(temp_dir):
                    if f.endswith('.desktop'):
                        with open(os.path.join(temp_dir, f), 'r') as df:
                            content = df.read()
                            name_match = re.search(r'^Name=(.*)$', content, re.MULTILINE)
                            if name_match: info['name'] = name_match.group(1).strip()
                            desc_match = re.search(r'^Comment=(.*)$', content, re.MULTILINE)
                            if desc_match: info['description'] = desc_match.group(1).strip()
                            break
        except Exception as e:
            print(f"Error extracting AppImage info: {e}")
        finally:
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
            
        return info
