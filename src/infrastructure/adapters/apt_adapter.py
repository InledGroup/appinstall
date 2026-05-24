import subprocess
from typing import List, Dict
from src.domain.ports import PackageManager

class AptAdapter(PackageManager):
    def search(self, query: str) -> List[Dict[str, str]]:
        results = []
        try:
            output = subprocess.check_output(['apt-cache', 'search', query], timeout=10).decode('utf-8')
            for line in output.split('\n'):
                if line.strip():
                    parts = line.split(' - ', 1)
                    name = parts[0].strip()
                    desc = parts[1].strip() if len(parts) > 1 else ""
                    results.append({'name': name, 'desc': desc, 'source': 'apt'})
        except:
            pass
        return results

    def list_installed(self) -> List[str]:
        try:
            output = subprocess.check_output(['dpkg', '--get-selections'], timeout=15).decode('utf-8')
            return [line.split()[0] for line in output.split('\n') 
                    if line.strip() and len(line.split()) > 1 and line.split()[1] == 'install']
        except:
            return []

    def install(self, package: str) -> List[str]:
        return ['pkexec', 'apt-get', 'install', '-y', package]

    def install_multiple(self, packages: List[str]) -> List[str]:
        return ['pkexec', 'apt-get', 'install', '-y'] + packages

    def install_local(self, file_path: str) -> List[str]:
        return ['pkexec', 'dpkg', '-i', file_path]

    def uninstall(self, package: str) -> List[str]:
        return ['pkexec', 'apt-get', 'remove', '-y', package]

    def update_cache(self) -> List[str]:
        return ['pkexec', 'apt-get', 'update']

    def clean_cache(self) -> List[str]:
        return ['pkexec', 'apt-get', 'clean']

    def autoremove(self) -> List[str]:
        return ['pkexec', 'apt-get', 'autoremove', '-y']

    def fix_broken(self) -> List[str]:
        return ['pkexec', 'apt-get', 'install', '-f', '-y']

    def get_cache_directory(self) -> str:
        return "/var/cache/apt/archives"

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        info = {'name': '', 'version': '', 'description': '', 'size': '', 'icon': ''}
        try:
            # Metadata
            cmd = ['dpkg-deb', '-f', file_path, 'Package', 'Version', 'Description', 'Installed-Size']
            output = subprocess.check_output(cmd).decode('utf-8')
            lines = output.split('\n')
            for line in lines:
                if line.startswith('Package:'): info['name'] = line.replace('Package:', '').strip()
                elif line.startswith('Version:'): info['version'] = line.replace('Version:', '').strip()
                elif line.startswith('Description:'): info['description'] = line.replace('Description:', '').strip()
                elif line.startswith('Installed-Size:'): info['size'] = line.replace('Installed-Size:', '').strip() + " KB"
            
            # Icon search (find the first icon in common paths)
            try:
                list_cmd = ['dpkg-deb', '-c', file_path]
                files = subprocess.check_output(list_cmd).decode('utf-8').split('\n')
                icon_path = None
                # Priority: hicolor/apps -> pixmaps -> any png/svg
                for f in files:
                    if '/usr/share/icons/hicolor/' in f and '/apps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                        icon_path = f.split()[-1].lstrip('.')
                        break
                if not icon_path:
                    for f in files:
                        if '/usr/share/pixmaps/' in f and (f.endswith('.png') or f.endswith('.svg')):
                            icon_path = f.split()[-1].lstrip('.')
                            break
                
                if icon_path:
                    import os, tempfile
                    temp_dir = os.path.join(tempfile.gettempdir(), 'appinstall_icons')
                    os.makedirs(temp_dir, exist_ok=True)
                    out_path = os.path.join(temp_dir, os.path.basename(icon_path))
                    
                    # Extract single file
                    extract_cmd = f"dpkg-deb --fsys-tarfile {file_path} | tar -x -O .{icon_path} > {out_path}"
                    subprocess.run(extract_cmd, shell=True, timeout=5)
                    info['icon'] = out_path
            except:
                pass
        except:
            pass
        return info

    def install_clamav(self) -> List[str]:
        return ['pkexec', 'apt-get', 'install', '-y', 'clamav', 'clamav-daemon', 'clamav-freshclam']
