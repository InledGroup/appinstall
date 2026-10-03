import os
import subprocess
import json
from typing import List, Dict
from src.domain.ports import PackageManager
from src.utils.system import BREW_PATH, HAS_BREW


class BrewAdapter(PackageManager):
    def __init__(self):
        self._meta_cache = {}

    def is_available(self) -> bool:
        return HAS_BREW

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.is_available():
            return []

        results = []
        try:
            output = subprocess.check_output(
                [BREW_PATH, 'search', query],
                timeout=10, stderr=subprocess.DEVNULL
            ).decode('utf-8')

            names = [n.strip() for n in output.split('\n') if n.strip()]
            if not names:
                return []

            batch = names[:15]
            try:
                info_cmd = [BREW_PATH, 'info', '--json=v2'] + batch
                raw = subprocess.check_output(
                    info_cmd, timeout=15, stderr=subprocess.DEVNULL
                ).decode('utf-8')
                info_data = json.loads(raw)
                formulas = {f['full_name']: f for f in info_data.get('formulae', [])}
                casks = {c['token']: c for c in info_data.get('casks', [])}
            except Exception:
                formulas = {}
                casks = {}

            for name in names[:15]:
                f = formulas.get(name)
                c = casks.get(name)
                meta = f or c

                if meta:
                    desc = meta.get('desc', '') or meta.get('description', '')
                    version = meta.get('versions', {}).get('stable', '') if f else meta.get('version', '')
                    self._meta_cache[name] = {
                        'description': desc,
                        'version': version,
                        'license': self._extract_license(meta),
                    }
                    results.append({
                        'name': name,
                        'display_name': meta.get('full_name', name),
                        'desc': desc,
                        'source': 'brew',
                        'icon': 'system-software-install-symbolic',
                    })
                else:
                    results.append({
                        'name': name,
                        'display_name': name,
                        'desc': '',
                        'source': 'brew',
                        'icon': 'system-software-install-symbolic',
                    })

        except Exception as e:
            print(f"Brew search error: {e}")

        return results

    def list_installed(self) -> List[str]:
        if not self.is_available():
            return []
        installed = []
        for subcommand in ['--formula', '--cask']:
            try:
                output = subprocess.check_output(
                    [BREW_PATH, 'list', subcommand],
                    timeout=10, stderr=subprocess.DEVNULL
                ).decode('utf-8')
                installed.extend(
                    n.strip() for n in output.split('\n') if n.strip()
                )
            except Exception:
                pass
        return installed

    def install(self, package: str) -> List[str]:
        return [BREW_PATH, 'install', package]

    def install_multiple(self, packages: List[str]) -> List[str]:
        return [BREW_PATH, 'install'] + packages

    def install_local(self, file_path: str) -> List[str]:
        return [BREW_PATH, 'install', '--formula', file_path]

    def uninstall(self, package: str) -> List[str]:
        return [BREW_PATH, 'uninstall', package]

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {
            'name': package_name,
            'version': 'N/A',
            'description': '',
            'size': 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'brew',
            'license': '',
        }

        cached = self._meta_cache.get(package_name, {})
        if cached:
            info['description'] = cached.get('description', '')
            info['version'] = cached.get('version', 'N/A')
            info['license'] = cached.get('license', '')

        if not self.is_available():
            return info

        try:
            raw = subprocess.check_output(
                [BREW_PATH, 'info', '--json=v2', package_name],
                timeout=10, stderr=subprocess.DEVNULL
            ).decode('utf-8')
            data = json.loads(raw)

            formula = None
            cask = None
            for f in data.get('formulae', []):
                if f.get('full_name') == package_name or f.get('name') == package_name:
                    formula = f
                    break
            if not formula:
                for c in data.get('casks', []):
                    if c.get('token') == package_name:
                        cask = c
                        break

            meta = formula or cask
            if meta:
                if formula:
                    info['version'] = formula.get('versions', {}).get('stable', 'N/A')
                    info['description'] = formula.get('desc', '')
                    info['license'] = self._extract_license(formula)
                    poured_bottle = formula.get('bottle', {}).get('stable', {})
                    files = poured_bottle.get('files', {})
                    total_bytes = sum(
                        v.get('size', 0) for v in files.values() if isinstance(v, dict)
                    )
                    if total_bytes:
                        info['size'] = f"{total_bytes / (1024*1024):.1f} MB"
                elif cask:
                    info['version'] = cask.get('version', 'N/A')
                    info['description'] = cask.get('desc', '')
                    info['license'] = cask.get('license', '')
                    stanza = cask.get('container', {})
                    if stanza and stanza.get('type') == 'zip':
                        info['size'] = stanza.get('size', 'N/A')

                self._meta_cache[package_name] = {
                    'description': info['description'],
                    'version': info['version'],
                    'license': info['license'],
                }

        except Exception as e:
            print(f"Brew info error for {package_name}: {e}")

        if info['version'] == 'N/A':
            try:
                out = subprocess.check_output(
                    [BREW_PATH, 'info', package_name],
                    timeout=5, stderr=subprocess.DEVNULL
                ).decode('utf-8')
                first_line = out.split('\n')[0] if out else ''
                if ':' in first_line:
                    info['version'] = first_line.split(':', 1)[1].strip().split(' ')[0]
            except Exception:
                pass

        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        return {
            'name': os.path.basename(file_path),
            'version': 'N/A',
            'description': 'Fórmula de Homebrew local',
            'size': f"{os.path.getsize(file_path) / 1024:.1f} KB" if os.path.exists(file_path) else 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'brew',
        }

    def update_cache(self) -> List[str]:
        return [BREW_PATH, 'update']

    def clean_cache(self) -> List[str]:
        return [BREW_PATH, 'cleanup']

    def autoremove(self) -> List[str]:
        return []

    def fix_broken(self) -> List[str]:
        return []

    def get_cache_directory(self) -> str:
        return os.path.expanduser("~/.cache/Homebrew")

    def install_clamav(self) -> List[str]:
        return []

    def upgrade_system(self) -> List[str]:
        return [BREW_PATH, 'upgrade']

    @staticmethod
    def _extract_license(meta: dict) -> str:
        license_obj = meta.get('license')
        if isinstance(license_obj, str):
            return license_obj
        if isinstance(license_obj, dict):
            return license_obj.get('identifier', str(license_obj))
        return ''
