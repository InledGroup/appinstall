import sys
import os
import subprocess
import shutil
import re
from typing import Optional, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import CLI_NAME
from src.cli_core import (
    COMMANDS, cmd_search, cmd_list, cmd_search_installed, cmd_install,
    cmd_remove, cmd_update, cmd_fix, cmd_info, _c
)


def _show_help():
    from src.utils.constants import CURRENT_VERSION
    print(f"""
{_c('bold', CLI_NAME)} {_c('dim', f'v{CURRENT_VERSION}')}  {_c('dim', '— Your friendly package manager')}

{_c('bold', ' USAGE')}
    {CLI_NAME} <command> [arguments]

{_c('bold', ' COMMANDS')}
    {_c('cyan', 'search')}  {_c('dim', '<query>')}       Search for packages
    {_c('cyan', 'list')}    {_c('dim', '[query]')}       List installed packages (optional filter)
    {_c('cyan', 'install')} {_c('dim', '<package>')}    Install a package
    {_c('cyan', 'remove')}  {_c('dim', '<package>')}    Remove a package
    {_c('cyan', 'update')}                 Update system packages
    {_c('cyan', 'fix')}                    Fix broken dependencies
    {_c('cyan', 'info')}    {_c('dim', '<package>')}    Show package details

{_c('bold', ' ALIASES')}
    {_c('dim', 'search')}    find, look
    {_c('dim', 'list')}      installed, apps
    {_c('dim', 'install')}   get, add
    {_c('dim', 'remove')}    uninstall, delete, purge
    {_c('dim', 'update')}    upgrade
    {_c('dim', 'fix')}       repair
    {_c('dim', 'info')}      details, show

{_c('bold', ' SMART SEARCH')}
    Multi-word queries are tried automatically:
    {_c('dim', f'{CLI_NAME} search wl clipboard')}   → also searches "wl-clipboard"
    {_c('dim', f'{CLI_NAME} search visual studio')} → also searches "visual-studio"

{_c('bold', ' PACKAGE SOURCES')}
    {_c('dim', 'Auto-detect:')}  {CLI_NAME} install firefox
    {_c('dim', 'Flatpak:')}      {CLI_NAME} install flatpak:org.gimp.GIMP
    {_c('dim', 'Snap:')}         {CLI_NAME} install snap:code
    {_c('dim', 'AUR:')}          {CLI_NAME} install aur:package-name
    {_c('dim', 'Local file:')}   {CLI_NAME} install /path/to/file.deb

{_c('bold', ' EXAMPLES')}
    {_c('green', f'{CLI_NAME} search firefox')}            {_c('dim', '# search in all sources')}
    {_c('green', f'{CLI_NAME} search wl clipboard')}      {_c('dim', '# smart search with variations')}
    {_c('green', f'{CLI_NAME} list')}                      {_c('dim', '# list all installed')}
    {_c('green', f'{CLI_NAME} list firefox')}              {_c('dim', '# search within installed packages')}
    {_c('green', f'{CLI_NAME} install firefox')}           {_c('dim', '# install from system repos')}
    {_c('green', f'{CLI_NAME} install flatpak:gimp')}     {_c('dim', '# install from Flathub')}
    {_c('green', f'{CLI_NAME} remove firefox')}            {_c('dim', '# remove a package')}
    {_c('green', f'{CLI_NAME} update')}                    {_c('dim', '# update everything')}
    {_c('green', f'{CLI_NAME} fix')}                       {_c('dim', '# fix broken dependencies')}
    {_c('green', f'{CLI_NAME} info firefox')}              {_c('dim', '# show package details')}
""")


def _detect_desktop_file_type(desktop_path: str) -> Tuple[bool, bool, bool]:
    try:
        with open(desktop_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        is_pwa = "X-AppInstall=PWA" in content or "--app=" in content or "--application-mode=" in content
        is_appimage = "X-AppInstall=AppImage" in content
        is_brew = "X-AppInstall=Homebrew" in content
        return is_pwa, is_appimage, is_brew
    except Exception:
        return False, False, False


def _owner_package_for_file(filepath: str) -> Optional[str]:
    if shutil.which('pacman'):
        try:
            out = subprocess.check_output(
                ['pacman', '-Qo', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            match = re.search(r'is owned by (\S+)', out)
            if not match:
                match = re.search(r'está contenido en (\S+)', out)
            if match:
                return match.group(1)
        except Exception:
            pass
    elif shutil.which('dpkg'):
        try:
            out = subprocess.check_output(
                ['dpkg', '-S', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            pkg = out.split(':')[0].strip()
            if pkg:
                return pkg
        except Exception:
            pass
    elif shutil.which('rpm'):
        try:
            out = subprocess.check_output(
                ['rpm', '-qf', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            if out.startswith('not owned'):
                return None
            return out.split('-')[0].split('.')[0]
        except Exception:
            pass
    return None


def _find_package_for_desktop(desktop_id: str) -> Optional[Tuple[str, str]]:
    app_id = desktop_id.replace(".desktop", "") if desktop_id.endswith(".desktop") else desktop_id

    try:
        from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
        fp = FlatpakAdapter()
        if fp.is_available():
            for pkg in fp.list_installed():
                if pkg == app_id or pkg == desktop_id:
                    return ("flatpak", pkg)
    except Exception:
        pass

    try:
        from src.infrastructure.adapters.snap_adapter import SnapAdapter
        sn = SnapAdapter()
        if sn.is_available():
            for pkg in sn.list_installed():
                if pkg == app_id or pkg == desktop_id:
                    return ("snap", pkg)
    except Exception:
        pass

    desktop_dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]

    for desktop_dir in desktop_dirs:
        target = os.path.join(desktop_dir, f"{app_id}.desktop")
        if os.path.exists(target):
            is_pwa, is_appimage, is_brew = _detect_desktop_file_type(target)
            if is_appimage:
                return ("appimage", app_id)
            if is_pwa:
                return ("pwa", app_id)
            if is_brew:
                return ("brew", app_id)

            pkg = _owner_package_for_file(target)
            if pkg:
                if shutil.which('pacman'):
                    try:
                        foreign = subprocess.check_output(
                            ['pacman', '-Qm'], stderr=subprocess.DEVNULL, timeout=5
                        ).decode('utf-8')
                        foreign_pkgs = {line.split()[0] for line in foreign.split('\n') if line.strip()}
                        if pkg in foreign_pkgs:
                            return ("aur", pkg)
                    except Exception:
                        pass
                return ("system", pkg)

    return None


def uninstall_by_desktop_id(desktop_id: str) -> Tuple[bool, str]:
    result = _find_package_for_desktop(desktop_id)
    if not result:
        return False, f"No package found for '{desktop_id}'"

    source, package_name = result

    try:
        from src.infrastructure.adapters.factory import get_package_manager
        from src.application.uninstall_service import UninstallService

        pm = get_package_manager()
        svc = UninstallService(pm)

        cmd = svc.get_uninstall_command(
            package_name,
            is_appimage=(source == "appimage"),
            is_brew=(source == "brew"),
            is_pwa=(source == "pwa"),
            brew_path=shutil.which('brew'),
            is_flatpak=(source == "flatpak"),
            is_snap=(source == "snap"),
            is_aur=(source == "aur")
        )

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            return True, f"'{package_name}' uninstalled successfully"
        else:
            stderr = proc.stderr.strip()
            return False, f"Failed to uninstall '{package_name}': {stderr}"

    except subprocess.TimeoutExpired:
        return False, "Uninstall timed out"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def handle_cli_args(argv: list) -> bool:
    if len(argv) < 2:
        _show_help()
        return False

    if argv[1] in ('-h', '--help', 'help'):
        _show_help()
        return False

    if argv[1] in ('--version', '-V', 'version'):
        from src.utils.constants import CURRENT_VERSION
        print(f"{CLI_NAME} v{CURRENT_VERSION}")
        return False

    if argv[1] == '--uninstall':
        if len(argv) < 3:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} --uninstall <desktop-id>')}", file=sys.stderr)
            return True
        desktop_id = argv[2]
        if not desktop_id.endswith(".desktop"):
            desktop_id += ".desktop"
        success, message = uninstall_by_desktop_id(desktop_id)
        print(f"  {message}")
        return not success

    command = argv[1].lower()
    args = argv[2:] if len(argv) > 2 else []

    if command not in COMMANDS:
        print(_c('red', f"  Unknown command: '{command}'"), file=sys.stderr)
        print(_c('dim', f"  Run '{CLI_NAME} help' for usage."), file=sys.stderr)
        return True

    func = COMMANDS[command]

    if command in ('search', 'find', 'look'):
        query = ' '.join(args) if args else ''
        if not query:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} {command} <query>')}", file=sys.stderr)
            return True
        return not func(query)
    elif command in ('list', 'installed', 'apps'):
        if args:
            query = ' '.join(args)
            return not cmd_search_installed(query)
        return not func()
    elif command in ('install', 'get', 'add',
                     'remove', 'uninstall', 'delete', 'purge',
                     'info', 'details', 'show'):
        if not args:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} {command} <argument>')}", file=sys.stderr)
            return True
        return not func(args[0])
    else:
        return not func()
