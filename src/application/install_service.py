import os
import subprocess
import threading
import shutil
import re
from gi.repository import GLib
from src.utils.system import HAS_BREW, BREW_PATH
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter

from src.infrastructure.services.localization import _

class InstallService:
    def __init__(self, package_manager):
        self.package_manager = package_manager
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()

    def get_pwa_command(self, url):
        """Busca el mejor navegador para ejecutar una PWA."""
        if shutil.which('epiphany'):
            return f'epiphany --application-mode="{url}"'
        elif shutil.which('google-chrome'):
            return f'google-chrome --app={url}'
        elif shutil.which('google-chrome-stable'):
            return f'google-chrome-stable --app={url}'
        elif shutil.which('chromium'):
            return f'chromium --app={url}'
        elif shutil.which('chromium-browser'):
            return f'chromium-browser --app={url}'
        elif shutil.which('brave'):
            return f'brave --app={url}'
        elif shutil.which('microsoft-edge'):
            return f'microsoft-edge --app={url}'
        return f'xdg-open {url}'

    def create_desktop_file_content(self, app_name, display_name, exec_cmd, target_icon_path, is_pwa=False):
        category = "Network;WebBrowser;" if is_pwa else "Utility;"
        install_type = "PWA" if is_pwa else "AppImage"
        
        return f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec={exec_cmd}
Icon={target_icon_path}
Terminal=false
Categories={category}
X-AppInstall={install_type}
X-SwiftInstall={install_type}
"""

    def get_install_command(self, file_path):
        if not file_path:
            return None

        # Check prefixes
        if file_path.startswith('flatpak:'):
            pkg_name = file_path.replace('flatpak:', '', 1)
            return self.flatpak_adapter.install(pkg_name)
        elif file_path.startswith('snap:'):
            pkg_name = file_path.replace('snap:', '', 1)
            return self.snap_adapter.install(pkg_name)
        elif file_path.startswith('aur:'):
            pkg_name = file_path.replace('aur:', '', 1)
            return self.aur_adapter.install(pkg_name)

        file_extension = os.path.splitext(file_path)[1].lower()
        is_brew_file = HAS_BREW and file_extension == '.rb'
        is_name_only = not file_extension

        # English: Check if it is a supported local package archive (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz)
        # Español: Comprobar si es un archivo de paquete local compatible (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz)
        is_local_package = (
            file_extension in ('.deb', '.rpm') or
            file_path.lower().endswith('.pkg.tar.zst') or
            file_path.lower().endswith('.pkg.tar.xz')
        )

        if is_local_package:
            return self.package_manager.install_local(file_path)
        elif is_brew_file:
            return [BREW_PATH, 'install', '--formula', file_path]
        elif is_name_only:
            if file_path.startswith('brew:'):
                pkg_name = file_path.replace('brew:', '', 1)
                return [BREW_PATH, 'install', pkg_name]
            else:
                return self.package_manager.install(file_path)
        elif file_extension in ('.tar.xz', '.tar.gz', '.tgz'):
            extract_dir = os.path.expanduser('~/.local')
            return ['tar', '-xvf', file_path, '-C', extract_dir]
        
        return None

    def get_appimage_install_command(self, file_path, display_name, icon_path):
        filename = os.path.basename(file_path)
        app_name = os.path.splitext(filename)[0].replace(" ", "_").lower()
        
        icon_ext = os.path.splitext(icon_path)[1].lower()
        if not icon_ext or icon_ext not in ['.png', '.jpg', '.jpeg', '.svg', '.ico']:
            icon_ext = '.png'
        target_icon_path = f"/usr/share/pixmaps/{app_name}{icon_ext}"
        
        exec_cmd = f"/usr/bin/{app_name}"
        desktop_content = self.create_desktop_file_content(app_name, display_name, exec_cmd, target_icon_path)
        escaped_content = desktop_content.replace("'", "'\\''")
        desktop_path = f"/usr/share/applications/{app_name}.desktop"
        
        return [
            'pkexec', 'bash', '-c',
            f'chmod +x "{file_path}" && ' +
            f'cp "{file_path}" /usr/bin/{app_name} && ' +
            f"cp '{icon_path}' '{target_icon_path}' && echo '{escaped_content}' > '{desktop_path}'"
        ]

    def get_pwa_install_command(self, display_name, url, icon_path):
        app_name = display_name.lower().replace(" ", "_").replace(".", "_")
        if not app_name:
            import time
            app_name = f"pwa_{int(time.time())}"
        
        exec_cmd = self.get_pwa_command(url)
        icon_ext = os.path.splitext(icon_path)[1].lower()
        if not icon_ext or icon_ext not in ['.png', '.jpg', '.jpeg', '.svg', '.ico']:
            icon_ext = '.png'
        
        target_icon_path = f"/usr/share/pixmaps/{app_name}{icon_ext}"
        desktop_content = self.create_desktop_file_content(app_name, display_name, exec_cmd, target_icon_path, is_pwa=True)
        escaped_content = desktop_content.replace("'", "'\\''")
        desktop_path = f"/usr/share/applications/{app_name}.desktop"
        
        return [
            'pkexec', 'bash', '-c',
            f"cp '{icon_path}' '{target_icon_path}' && echo '{escaped_content}' > '{desktop_path}'"
        ]

    def run_installation(self, cmd, file_path, on_progress, on_complete):
        def _run():
            try:
                # Copy current environment and configure privilege escalation to use pkexec (graphical sudo)
                env = os.environ.copy()
                env["SUDO"] = "pkexec"
                env["PACMAN"] = "pkexec pacman"
                process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    # English: Determine success message based on context
                    # Español: Determinar el mensaje de éxito según el contexto
                    if file_path == "system_upgrade":
                        message = _("El sistema se ha actualizado correctamente.")
                    elif file_path and file_path.lower().endswith('.appimage'):
                        filename = os.path.basename(file_path)
                        app_name = os.path.splitext(filename)[0]
                        message = _("AppImage instalado como {}. Se ha creado un acceso directo.").format(app_name)
                    elif not file_path:
                        message = _("¡Web App creada correctamente! Ya la tienes disponible en tu menú.")
                    else:
                        message = _("He instalado todo bien, ¡disfrútala!")
                    
                    GLib.idle_add(on_complete, message, False, "")
                else:
                    GLib.idle_add(on_complete, _("Vaya, he encontrado un error al instalar: {}").format(stderr), True, stderr)
            except Exception as e:
                GLib.idle_add(on_complete, _("Error en la instalación: {}").format(str(e)), True, "")

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

    def run_fix_deps(self, cmd, on_progress, on_complete):
        def _run():
            try:
                # Copy current environment and configure privilege escalation to use pkexec (graphical sudo)
                env = os.environ.copy()
                env["SUDO"] = "pkexec"
                env["PACMAN"] = "pkexec pacman"
                process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    GLib.idle_add(on_complete, _("He arreglado las dependencias"))
                else:
                    GLib.idle_add(on_complete, _("Vaya, un error al corregir dependencias: {}").format(stderr), True)
            except Exception as e:
                GLib.idle_add(on_complete, _("Error al corregir dependencias: {}").format(str(e)), True)

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
