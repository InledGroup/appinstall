import sys
import subprocess
import shutil
import os
from typing import Optional, List, Dict


# ── Colors ──────────────────────────────────────────────────────────────────

_COLORS = {
    'reset':   '\033[0m',
    'bold':    '\033[1m',
    'dim':     '\033[2m',
    'cyan':    '\033[36m',
    'green':   '\033[32m',
    'yellow':  '\033[33m',
    'magenta': '\033[35m',
    'blue':    '\033[34m',
    'red':     '\033[31m',
    'white':   '\033[97m',
    'gray':    '\033[90m',
}

def _c(color: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


# ── Adapters ────────────────────────────────────────────────────────────────

def _get_adapters():
    from src.infrastructure.adapters.factory import get_package_manager
    from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
    from src.infrastructure.adapters.snap_adapter import SnapAdapter
    from src.infrastructure.adapters.aur_adapter import AurAdapter

    pm = get_package_manager()
    adapters = {'system': pm}

    fp = FlatpakAdapter()
    if fp.is_available():
        adapters['flatpak'] = fp

    sn = SnapAdapter()
    if sn.is_available():
        adapters['snap'] = sn

    if shutil.which('pacman'):
        adapters['aur'] = AurAdapter()

    return adapters


SOURCE_LABELS = {
    'system':  ('sys', _c('blue',   'sys')),
    'flatpak': ('fpk', _c('green',  'fpk')),
    'snap':    ('snap', _c('magenta', 'snap')),
    'aur':     ('aur', _c('yellow', 'aur')),
}


def _parse_source(query: str):
    for prefix in ['flatpak:', 'snap:', 'aur:', 'pacman:', 'brew:']:
        if query.lower().startswith(prefix):
            return prefix.rstrip(':'), query[len(prefix):]
    return None, query


def _generate_search_variations(query: str) -> List[str]:
    """Generate smart variations of a search query.
    
    "wl clipboard" → ["wl clipboard", "wl-clipboard", "wlclipboard"]
    "visual studio code" → ["visual studio code", "visual-studio-code", "visualstudiocode"]
    """
    variations = [query]
    if ' ' in query:
        variations.append(query.replace(' ', '-'))
        variations.append(query.replace(' ', ''))
    return list(dict.fromkeys(variations))


def _run_cmd(cmd, timeout=120):
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        for line in proc.stdout:
            print(line, end='')
        proc.wait(timeout=timeout)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        print(_c('red', "Timed out."), file=sys.stderr)
        return False
    except Exception as e:
        print(_c('red', f"Error: {e}"), file=sys.stderr)
        return False


# ── Format helpers ──────────────────────────────────────────────────────────

def _print_search_results(results_by_source: Dict[str, list], query: str):
    """Print search results grouped by source with nice formatting."""
    total = sum(len(r) for r in results_by_source.values())
    if total == 0:
        print(_c('dim', f"  No results for ") + _c('bold', f"'{query}'"))
        return

    print(_c('dim', f"  Found ") + _c('bold', str(total)) + _c('dim', f" results for ") + _c('bold', f"'{query}'"))
    print()

    for source, results in results_by_source.items():
        if not results:
            continue
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('bold', colored_label)}  {_c('dim', f'({len(results)} packages)')}")
        print(f"  {_c('dim', '─' * 50)}")
        for r in results:
            name = r.get('name', '')
            desc = r.get('desc', '')
            print(f"    {_c('white', name)}")
            if desc:
                # Truncate long descriptions
                if len(desc) > 70:
                    desc = desc[:67] + '...'
                print(f"    {_c('dim', desc)}")
        print()


def _print_installed_list(packages_by_source: Dict[str, list]):
    """Print installed packages grouped by source."""
    total = sum(len(p) for p in packages_by_source.values())
    print(_c('bold', '  Installed packages'))
    print(_c('dim', '  ─' * 25))
    print()

    for source, packages in packages_by_source.items():
        if not packages:
            continue
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('bold', colored_label)}  {_c('dim', f'({len(packages)} packages)')}")
        for pkg in sorted(packages):
            print(f"    {pkg}")
        print()

    print(_c('dim', '  Total: ') + _c('bold', str(total)) + _c('dim', ' packages'))


def _print_package_info(info: dict, source: str = None):
    """Print package info in a structured card format."""
    name = info.get('name', 'unknown')
    version = info.get('version', '')
    desc = info.get('description', '')
    size = info.get('size', '')
    developer = info.get('developer', '')
    license_ = info.get('license', '')

    print()
    print(f"  {_c('bold', _c('white', name))}")
    if source:
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('dim', 'source:')}  {colored_label}")
    if version:
        print(f"  {_c('dim', 'version:')} {_c('green', version)}")
    if desc:
        print(f"  {_c('dim', 'about:')}  {desc}")
    if developer:
        print(f"  {_c('dim', 'by:')}     {developer}")
    if license_:
        print(f"  {_c('dim', 'license:')} {license_}")
    if size:
        print(f"  {_c('dim', 'size:')}   {size}")
    print()


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_search(query: str):
    if not query:
        print(f"  Usage: {_c('bold', 'appi search <query>')}", file=sys.stderr)
        print(f"  Example: {_c('dim', 'appi search wl clipboard')}", file=sys.stderr)
        return False

    adapters = _get_adapters()
    variations = _generate_search_variations(query)
    results_by_source = {}

    for source, adapter in adapters.items():
        try:
            seen = set()
            all_results = []
            for variation in variations:
                results = adapter.search(variation)
                for r in results:
                    name = r.get('name', '')
                    if name not in seen:
                        seen.add(name)
                        all_results.append(r)
            results_by_source[source] = all_results
        except Exception:
            results_by_source[source] = []

    _print_search_results(results_by_source, query)
    return any(results_by_source.values())


def cmd_list(filter_source: Optional[str] = None):
    adapters = _get_adapters()
    packages_by_source = {}

    for source, adapter in adapters.items():
        if filter_source and source != filter_source:
            continue
        try:
            packages = adapter.list_installed()
            if packages:
                packages_by_source[source] = packages
        except Exception:
            pass

    _print_installed_list(packages_by_source)
    return True


def cmd_install(package: str):
    if not package:
        print(f"  Usage: {_c('bold', 'appi install <package>')}", file=sys.stderr)
        print(f"  Examples:", file=sys.stderr)
        print(f"    {_c('dim', 'appi install firefox')}          {_c('dim', '# auto-detect source')}", file=sys.stderr)
        print(f"    {_c('dim', 'appi install flatpak:org.gimp.GIMP')}", file=sys.stderr)
        print(f"    {_c('dim', 'appi install snap:code')}", file=sys.stderr)
        print(f"    {_c('dim', 'appi install /path/to/file.deb')}", file=sys.stderr)
        return False

    if os.path.isfile(package):
        return _install_file(package)

    source, name = _parse_source(package)
    adapters = _get_adapters()

    if source and source in adapters:
        cmd = adapters[source].install(name)
        print(f"  {_c('cyan', 'Installing')} {_c('bold', name)} {_c('dim', f'from {source}...')}")
        return _run_cmd(cmd)

    # Try with variations
    variations = _generate_search_variations(name)
    for source, adapter in adapters.items():
        try:
            installed = adapter.list_installed()
            for variation in variations:
                if variation in installed:
                    cmd = adapter.uninstall(variation)
                    print(f"  {_c('cyan', 'Installing')} {_c('bold', variation)} {_c('dim', f'from {source}...')}")
                    return _run_cmd(cmd)
            results = adapter.search(variations[0])
            if results and results[0].get('name') in variations:
                match_name = results[0]['name']
                cmd = adapter.install(match_name)
                print(f"  {_c('cyan', 'Installing')} {_c('bold', match_name)} {_c('dim', f'from {source}...')}")
                return _run_cmd(cmd)
        except Exception:
            pass

    if 'system' in adapters:
        cmd = adapters['system'].install(name)
        print(f"  {_c('cyan', 'Installing')} {_c('bold', name)} {_c('dim', 'from system repos...')}")
        return _run_cmd(cmd)

    print(_c('red', f"  Could not find '{package}' in any source."), file=sys.stderr)
    return False


def _install_file(file_path: str):
    adapters = _get_adapters()

    if file_path.endswith('.deb') and 'system' in adapters:
        cmd = ['pkexec', 'dpkg', '-i', file_path]
    elif file_path.endswith('.rpm') and 'system' in adapters:
        cmd = ['pkexec', 'rpm', '-i', file_path]
    elif file_path.endswith('.pkg.tar.zst') or file_path.endswith('.pkg.tar.xz'):
        cmd = ['pkexec', 'pacman', '-U', '--noconfirm', file_path]
    elif file_path.endswith('.flatpakref') or file_path.endswith('.flatpak'):
        if 'flatpak' in adapters:
            cmd = adapters['flatpak'].install_local(file_path)
        else:
            cmd = ['pkexec', 'flatpak', 'install', '-y', file_path]
    elif file_path.endswith('.AppImage'):
        name = os.path.splitext(os.path.basename(file_path))[0]
        cmd = ['pkexec', 'bash', '-c',
               f'cp "{file_path}" /usr/bin/{name} && '
               f'chmod +x /usr/bin/{name}']
    else:
        print(_c('red', f"  Unknown file type: {file_path}"), file=sys.stderr)
        return False

    print(f"  {_c('cyan', 'Installing from file:')} {_c('bold', file_path)}")
    return _run_cmd(cmd)


def cmd_remove(package: str):
    if not package:
        print(f"  Usage: {_c('bold', 'appi remove <package>')}", file=sys.stderr)
        print(f"  Examples:", file=sys.stderr)
        print(f"    {_c('dim', 'appi remove firefox')}", file=sys.stderr)
        print(f"    {_c('dim', 'appi remove flatpak:org.gimp.GIMP')}", file=sys.stderr)
        return False

    source, name = _parse_source(package)
    adapters = _get_adapters()

    if source and source in adapters:
        cmd = adapters[source].uninstall(name)
        print(f"  {_c('red', 'Removing')} {_c('bold', name)} {_c('dim', f'from {source}...')}")
        return _run_cmd(cmd)

    # Try with variations
    variations = _generate_search_variations(name)
    for source, adapter in adapters.items():
        try:
            installed = adapter.list_installed()
            for variation in variations:
                if variation in installed:
                    cmd = adapter.uninstall(variation)
                    print(f"  {_c('red', 'Removing')} {_c('bold', variation)} {_c('dim', f'from {source}...')}")
                    return _run_cmd(cmd)
        except Exception:
            pass

    if 'system' in adapters:
        cmd = adapters['system'].uninstall(name)
        print(f"  {_c('red', 'Removing')} {_c('bold', name)} {_c('dim', 'from system...')}")
        return _run_cmd(cmd)

    print(_c('red', f"  Package '{package}' not found."), file=sys.stderr)
    return False


def cmd_update():
    adapters = _get_adapters()

    print(_c('bold', '  Updating system packages...'))
    print()

    for source, adapter in adapters.items():
        try:
            cmd = adapter.upgrade_system()
            if cmd:
                label, colored_label = SOURCE_LABELS.get(source, (source, source))
                print(f"  {colored_label}")
                _run_cmd(cmd)
        except Exception:
            pass

    return True


def cmd_info(package: str):
    if not package:
        print(f"  Usage: {_c('bold', 'appi info <package>')}", file=sys.stderr)
        print(f"  Example: {_c('dim', 'appi info firefox')}", file=sys.stderr)
        return False

    source, name = _parse_source(package)
    adapters = _get_adapters()

    if source and source in adapters:
        try:
            info = adapters[source].get_package_info(name)
            _print_package_info(info, source)
            return True
        except Exception as e:
            print(_c('red', f"  Error: {e}"), file=sys.stderr)
            return False

    # Try with variations
    variations = _generate_search_variations(name)
    for source, adapter in adapters.items():
        try:
            for variation in variations:
                info = adapter.get_package_info(variation)
                if info.get('version') and info['version'] != 'N/A':
                    _print_package_info(info, source)
                    return True
        except Exception:
            pass

    print(_c('red', f"  Package '{package}' not found."), file=sys.stderr)
    return False


# ── Command registry ────────────────────────────────────────────────────────

COMMANDS = {
    'search':    cmd_search,
    'find':      cmd_search,
    'look':      cmd_search,
    'list':      cmd_list,
    'installed': cmd_list,
    'apps':      cmd_list,
    'install':   cmd_install,
    'get':       cmd_install,
    'add':       cmd_install,
    'remove':    cmd_remove,
    'uninstall': cmd_remove,
    'delete':    cmd_remove,
    'purge':     cmd_remove,
    'update':    lambda: cmd_update(),
    'upgrade':   lambda: cmd_update(),
    'info':      cmd_info,
    'details':   cmd_info,
    'show':      cmd_info,
}
