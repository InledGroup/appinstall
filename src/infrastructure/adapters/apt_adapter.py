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

    def install_clamav(self) -> List[str]:
        return ['pkexec', 'apt-get', 'install', '-y', 'clamav', 'clamav-daemon', 'clamav-freshclam']
