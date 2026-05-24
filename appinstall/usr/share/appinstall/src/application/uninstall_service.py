import subprocess
import threading
import os
from gi.repository import GLib
from src.domain.ports import PackageManager

class UninstallService:
    def __init__(self, package_manager: PackageManager):
        self.package_manager = package_manager

    def get_uninstall_command(self, package_name, is_appimage=False, is_brew=False, is_pwa=False, brew_path=None):
        if is_appimage:
            return [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/bin/{package_name} && ' +
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.*'
            ]
        elif is_pwa:
            return [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.*'
            ]
        elif is_brew:
            return [brew_path, 'uninstall', package_name]
        else:
            return self.package_manager.uninstall(package_name)

    def run_uninstall(self, cmd, on_progress, on_complete):
        def _run():
            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        GLib.idle_add(on_progress)
                
                _, stderr = process.communicate()
                
                if process.returncode == 0:
                    GLib.idle_add(on_complete, True, None)
                else:
                    GLib.idle_add(on_complete, False, str(stderr))
            except Exception as e:
                GLib.idle_add(on_complete, False, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
