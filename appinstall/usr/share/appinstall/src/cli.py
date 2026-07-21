import sys
import os
import subprocess
import shutil
import re
from typing import Optional, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


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
    if len(argv) < 3:
        print("Usage: appinstall --uninstall <desktop-id>", file=sys.stderr)
        print("Example: appinstall --uninstall org.gimp.GIMP", file=sys.stderr)
        return True

    if argv[1] == "--uninstall":
        desktop_id = argv[2]
        if not desktop_id.endswith(".desktop"):
            desktop_id += ".desktop"

        success, message = uninstall_by_desktop_id(desktop_id)
        print(message)
        return not success

    return False
