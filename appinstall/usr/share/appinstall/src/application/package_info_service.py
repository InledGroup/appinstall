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
            # English: Check for supported system packages (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz, .pkg.tar.gz, .pkg.tar, .pacman)
            # Español: Comprobar si son paquetes de sistema compatibles (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz, .pkg.tar.gz, .pkg.tar, .pacman)
            is_local_pkg = (
                ext in ('.deb', '.rpm', '.pacman') or
                identifier.lower().endswith('.pkg.tar.zst') or
                identifier.lower().endswith('.pkg.tar.xz') or
                identifier.lower().endswith('.pkg.tar.gz') or
                identifier.lower().endswith('.pkg.tar')
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
            elif identifier.startswith('gnome-ext:') or identifier.startswith('gnome-extension:'):
                prefix = 'gnome-ext:' if identifier.startswith('gnome-ext:') else 'gnome-extension:'
                ext_id = identifier.replace(prefix, '', 1)
                return self._get_gnome_extension_info(ext_id)
            return self.package_manager.get_package_info(identifier)
        
        return {}

    def _get_gnome_extension_info(self, ext_id: str) -> Dict[str, str]:
        """Fetch details for a GNOME Extension from local metadata or EGO."""
        import json
        import urllib.request
        from src.utils.system import get_cached_icon

        # 1. Check if extension exists locally
        user_ext_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{ext_id}")
        sys_ext_dir = f"/usr/share/gnome-shell/extensions/{ext_id}"
        meta_path = None
        if os.path.isfile(os.path.join(user_ext_dir, "metadata.json")):
            meta_path = os.path.join(user_ext_dir, "metadata.json")
        elif os.path.isfile(os.path.join(sys_ext_dir, "metadata.json")):
            meta_path = os.path.join(sys_ext_dir, "metadata.json")

        info = {
            'name': ext_id,
            'version': 'N/A',
            'description': '',
            'developer': 'GNOME Community',
            'license': 'GPL',
            'size': 'N/A',
            'icon': 'application-x-addon-symbolic',
            'source': 'gnome-ext',
            'uuid': ext_id,
            'is_installed': meta_path is not None,
            'verified': True,
        }

        if meta_path:
            try:
                with open(meta_path, 'r', encoding='utf-8', errors='ignore') as f:
                    local_meta = json.load(f)
                    info['name'] = local_meta.get('name', ext_id)
                    info['description'] = local_meta.get('description', '')
                    info['version'] = str(local_meta.get('version', 'N/A'))
                    if local_meta.get('url'):
                        info['website'] = local_meta.get('url')
                    if local_meta.get('uuid'):
                        info['uuid'] = local_meta.get('uuid')
            except Exception as e:
                print(f"Error reading local extension metadata: {e}")

        # 2. Query EGO to enrich description, author, icon, demo screenshot, and downloads
        try:
            ego_url = f"https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(ext_id)}"
            req = urllib.request.Request(ego_url, headers={"User-Agent": "AppInstall/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                exts = data.get('extensions', [])
                matched = None
                for e in exts:
                    if e.get('uuid', '').lower() == ext_id.lower() or str(e.get('pk', '')) == str(ext_id):
                        matched = e
                        break
                if not matched:
                    for e in exts:
                        if e.get('name', '').strip().lower() == ext_id.strip().lower():
                            matched = e
                            break

                if matched:
                    pk = matched.get('pk')
                    info_data = matched
                    try:
                        info_url = f"https://extensions.gnome.org/extension-info/?pk={pk}"
                        info_req = urllib.request.Request(info_url, headers={"User-Agent": "AppInstall/1.0"})
                        with urllib.request.urlopen(info_req, timeout=5) as info_resp:
                            info_data = json.loads(info_resp.read().decode('utf-8'))
                    except Exception:
                        pass

                    desc = info_data.get('description') or matched.get('description', '')
                    if desc and (not info['description'] or len(desc) > len(info['description'])):
                        info['description'] = desc
                    if not info['name'] or info['name'] == ext_id:
                        info['name'] = info_data.get('name') or matched.get('name', ext_id)
                    info['developer'] = info_data.get('creator') or matched.get('creator', info['developer'])
                    if not info.get('website'):
                        link = info_data.get('link') or matched.get('link', '')
                        info['website'] = f"https://extensions.gnome.org{link}" if link else ""
                    
                    # Supported Shell Versions & Compatibility
                    from src.utils.system import check_gnome_shell_compatibility
                    shell_map = info_data.get('shell_version_map', {})
                    is_comp, badge_text, tooltip = check_gnome_shell_compatibility(shell_map)
                    info['is_shell_compatible'] = is_comp
                    info['shell_compat_badge'] = badge_text
                    info['shell_compat_tooltip'] = tooltip
                    info['supported_shell_versions'] = list(shell_map.keys())

                    # Downloads count
                    dls = info_data.get('downloads') or matched.get('downloads', 0)
                    if dls:
                        info['downloads'] = dls

                    # Icon (supports SVG, GIF, PNG, WebP)
                    from src.utils.system import get_cached_icon, get_cached_screenshot
                    icon_rel = info_data.get('icon') or matched.get('icon', '')
                    if icon_rel and not icon_rel.endswith('plugin.png'):
                        full_icon_url = f"https://extensions.gnome.org{icon_rel}" if icon_rel.startswith('/') else icon_rel
                        cached = get_cached_icon(full_icon_url, f"ego_{pk or ext_id}")
                        if cached and os.path.exists(cached):
                            info['icon'] = cached

                    # Demo Screenshot / Image (get latest screenshot)
                    screenshot_rel = info_data.get('screenshot') or matched.get('screenshot', '')
                    if screenshot_rel and not screenshot_rel.endswith('plugin.png') and screenshot_rel != icon_rel:
                        full_shot_url = f"https://extensions.gnome.org{screenshot_rel}" if screenshot_rel.startswith('/') else screenshot_rel
                        cached_shot = get_cached_screenshot(full_shot_url, f"ego_shot_{pk or ext_id}")
                        if cached_shot and os.path.exists(cached_shot):
                            try:
                                import gi
                                gi.require_version('GdkPixbuf', '2.0')
                                from gi.repository import GdkPixbuf
                                pix = GdkPixbuf.Pixbuf.new_from_file(cached_shot)
                                if pix and pix.get_width() >= 180 and pix.get_height() >= 100:
                                    info['cached_screenshots'] = [cached_shot]
                            except Exception:
                                info['cached_screenshots'] = [cached_shot]
        except Exception as e:
            print(f"Error querying EGO for extension info ({ext_id}): {e}")

        if 'is_shell_compatible' not in info and meta_path:
            try:
                from src.utils.system import check_gnome_shell_compatibility
                is_comp, badge_text, tooltip = check_gnome_shell_compatibility(local_meta.get('shell-version', []))
                info['is_shell_compatible'] = is_comp
                info['shell_compat_badge'] = badge_text
                info['shell_compat_tooltip'] = tooltip
                info['supported_shell_versions'] = local_meta.get('shell-version', [])
            except Exception:
                pass

        return info

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
