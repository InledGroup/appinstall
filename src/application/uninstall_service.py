import threading
import os
from gi.repository import GLib
from src.domain.ports import PackageManager
from src.application import prompt_engine
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter
from src.infrastructure.services.localization import _

class UninstallService:
    def __init__(self, package_manager: PackageManager):
        self.package_manager = package_manager
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()
        # English: Last command/environment and any question the manager asked
        # Español: Último comando/entorno y cualquier pregunta del gestor
        self.last_cmd = None
        self.last_env = None
        self.blocked_prompt = None

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

    def run_uninstall(self, cmd, on_progress=None, on_complete=None, on_log=None, cancel_token=None):
        def _run():
            try:
                env = self._prepare_env()
                self.last_cmd = list(cmd)
                self.last_env = env
                self.blocked_prompt = None

                def emit(line):
                    if on_log:
                        GLib.idle_add(on_log, line)
                    elif on_progress:
                        GLib.idle_add(on_progress)

                returncode, log_lines, blocked = prompt_engine.run_command(
                    cmd, env=env, on_log=emit, cancel_token=cancel_token
                )
                self.blocked_prompt = blocked

                if cancel_token is not None and cancel_token.was_terminated():
                    if on_complete:
                        GLib.idle_add(on_complete, False, _("Operación cancelada por el usuario."))
                    return

                if returncode == 0 and not blocked:
                    prompt_engine.clear_failure()
                else:
                    prompt_engine.record_failure(self.last_cmd, env)

                stderr = "\n".join(log_lines[-20:]) if log_lines else ""

                if returncode == 0:
                    if on_complete:
                        GLib.idle_add(on_complete, True, None)
                else:
                    if blocked:
                        stderr = _("El gestor de paquetes ha hecho una pregunta que necesitaba tu respuesta:\n{}").format(blocked)
                    if on_complete:
                        GLib.idle_add(on_complete, False, stderr or "Error en la ejecución del comando de desinstalación")
            except Exception as e:
                if on_complete:
                    GLib.idle_add(on_complete, False, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
