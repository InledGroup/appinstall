import subprocess
import threading
import os
from gi.repository import GLib
from src.domain.ports import PackageManager
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter

class UninstallService:
    def __init__(self, package_manager: PackageManager):
        self.package_manager = package_manager
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()

    def get_uninstall_command(self, package_name, is_appimage=False, is_brew=False, is_pwa=False, brew_path=None, is_flatpak=False, is_snap=False, is_aur=False):
        if is_flatpak or package_name.startswith('flatpak:'):
            pkg_name = package_name.replace('flatpak:', '', 1)
            return self.flatpak_adapter.uninstall(pkg_name)
        elif is_snap or package_name.startswith('snap:'):
            pkg_name = package_name.replace('snap:', '', 1)
            return self.snap_adapter.uninstall(pkg_name)
        elif is_aur or package_name.startswith('aur:'):
            pkg_name = package_name.replace('aur:', '', 1)
            return self.aur_adapter.uninstall(pkg_name)
        elif is_appimage:
            return [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/bin/{package_name} && ' +
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.*'
            ]
        elif is_pwa:
            user_desktop = os.path.expanduser(f"~/.local/share/applications/{package_name}.desktop")
            return [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.* && ' +
                f'rm -f "{user_desktop}"'
            ]
        elif is_brew:
            return [brew_path, 'uninstall', package_name]
        else:
            return self.package_manager.uninstall(package_name)

    def _prepare_env(self):
        env = os.environ.copy()
        env["SUDO"] = "pkexec"
        env["PACMAN"] = "pacman"
        env["PACMAN_AUTH"] = "pkexec"
        env["APPINSTALL_SUDO"] = "pkexec"
        return env

    def run_uninstall(self, cmd, on_progress=None, on_complete=None, on_log=None):
        def _run():
            try:
                env = self._prepare_env()
                process = subprocess.Popen(
                    cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True, bufsize=1
                )
                
                log_lines = []
                for line in process.stdout:
                    stripped = line.rstrip('\n')
                    if stripped.strip():
                        log_lines.append(stripped)
                        if on_log:
                            GLib.idle_add(on_log, stripped)
                        elif on_progress:
                            GLib.idle_add(on_progress)
                
                process.wait()
                returncode = process.returncode
                stderr = "\n".join(log_lines[-20:]) if log_lines else ""
                
                if returncode == 0:
                    if on_complete:
                        GLib.idle_add(on_complete, True, None)
                else:
                    if on_complete:
                        GLib.idle_add(on_complete, False, stderr or "Error en la ejecución del comando de desinstalación")
            except Exception as e:
                if on_complete:
                    GLib.idle_add(on_complete, False, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
