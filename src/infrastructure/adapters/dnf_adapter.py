import subprocess
from typing import List, Dict
from src.domain.ports import PackageManager

class DnfAdapter(PackageManager):
    def search(self, query: str) -> List[Dict[str, str]]:
        results = []
        try:
            output = subprocess.check_output(['dnf', 'search', '--quiet', query], timeout=30).decode('utf-8', errors='ignore')
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if ' : ' in line:
                    parts = line.split(' : ', 1)
                    name = parts[0].strip()
                    archs = ('.x86_64', '.i686', '.noarch', '.armv7hl', '.aarch64', '.ppc64le', '.s390x')
                    for arch in archs:
                        if name.endswith(arch):
                            name = name[:-len(arch)]
                            break
                    desc = parts[1].strip()
                    results.append({'name': name, 'desc': desc, 'source': 'dnf'})
                elif '|' in line and not line.startswith('---'):
                    parts = line.split('|', 1)
                    name = parts[0].strip()
                    desc = parts[1].strip()
                    if name.lower() not in ('id', 'nombre', 'name'):
                        results.append({'name': name, 'desc': desc, 'source': 'dnf'})
        except Exception as e:
            print(f"Error en dnf search: {e}")
        return results

    def list_installed(self) -> List[str]:
        try:
            output = subprocess.check_output(['rpm', '-qa', '--qf', '%{NAME}\\n'], timeout=15).decode('utf-8')
            return [line.strip() for line in output.split('\n') if line.strip()]
        except:
            return []

    def install(self, package: str) -> List[str]:
        return ['pkexec', 'dnf', 'install', '-y', package]

    def install_multiple(self, packages: List[str]) -> List[str]:
        return ['pkexec', 'dnf', 'install', '-y'] + packages

    def install_local(self, file_path: str) -> List[str]:
        return ['pkexec', 'dnf', 'install', '-y', file_path]

    def uninstall(self, package: str) -> List[str]:
        return ['pkexec', 'dnf', 'remove', '-y', package]

    def update_cache(self) -> List[str]:
        return ['pkexec', 'dnf', 'makecache']

    def clean_cache(self) -> List[str]:
        return ['pkexec', 'dnf', 'clean', 'all']

    def autoremove(self) -> List[str]:
        return ['pkexec', 'dnf', 'autoremove', '-y']

    def fix_broken(self) -> List[str]:
        return ['pkexec', 'dnf', 'check']

    def get_cache_directory(self) -> str:
        return "/var/cache/dnf"

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        info = {'name': '', 'version': '', 'description': '', 'size': '', 'icon': ''}
        try:
            # Metadata
            cmd = ['rpm', '-qp', '--qf', '%{NAME}\n%{VERSION}\n%{SUMMARY}\n%{SIZE}', file_path]
            output = subprocess.check_output(cmd).decode('utf-8')
            lines = output.split('\n')
            if len(lines) >= 4:
                info['name'] = lines[0].strip()
                info['version'] = lines[1].strip()
                info['description'] = lines[2].strip()
                size_bytes = int(lines[3].strip())
                info['size'] = f"{size_bytes / 1024:.1f} KB"
            
            # Icon search (find the first icon in common paths)
            try:
                list_cmd = ['rpm', '-qpl', file_path]
                files = subprocess.check_output(list_cmd).decode('utf-8').split('\n')
                icon_path = None
                for f in files:
                    if '/usr/share/icons/hicolor/' in f and '/apps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                        icon_path = f.strip()
                        break
                if not icon_path:
                    for f in files:
                        if '/usr/share/pixmaps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                            icon_path = f.strip()
                            break
                
                if icon_path:
                    import os, tempfile
                    temp_dir = os.path.join(tempfile.gettempdir(), 'appinstall_icons')
                    os.makedirs(temp_dir, exist_ok=True)
                    out_path = os.path.join(temp_dir, os.path.basename(icon_path))
                    
                    # Extract single file using rpm2cpio
                    extract_cmd = f"rpm2cpio {file_path} | cpio -iv --to-stdout .{icon_path} > {out_path}"
                    subprocess.run(extract_cmd, shell=True, timeout=5)
                    info['icon'] = out_path
            except:
                pass
        except:
            pass
        return info

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {'name': package_name, 'version': '', 'description': '', 'size': '', 'icon': ''}
        try:
            output = subprocess.check_output(['dnf', 'info', '--quiet', package_name]).decode('utf-8', errors='ignore')
            for line in output.split('\n'):
                if line.startswith('Version'): info['version'] = line.split(':', 1)[1].strip()
                elif line.startswith('Description') or line.startswith('Summary'):
                    info['description'] = line.split(':', 1)[1].strip()
                elif line.startswith('Size'):
                    info['size'] = line.split(':', 1)[1].strip()
            
            # Simple icon heuristic
            from gi.repository import Gtk, Gdk
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            if theme.has_icon(package_name):
                info['icon'] = package_name
        except:
            pass
        return info

    def install_clamav(self) -> List[str]:
        return ['pkexec', 'dnf', 'install', '-y', 'clamav', 'clamav-update', 'clamd']

    def upgrade_system(self) -> List[str]:
        # English: Run DNF cache update followed by system upgrade
        # Español: Ejecutar la actualización de caché de DNF seguida de la actualización del sistema
        return ['pkexec', 'sh', '-c', 'dnf makecache && dnf upgrade -y']

