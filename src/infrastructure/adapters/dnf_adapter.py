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

    def install_clamav(self) -> List[str]:
        return ['pkexec', 'dnf', 'install', '-y', 'clamav', 'clamav-update', 'clamd']
