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
from src.infrastructure.adapters.pulsar_store_adapter import PulsarStoreAdapter

from src.infrastructure.services.localization import _

class InstallService:
    def __init__(self, package_manager):
        self.package_manager = package_manager
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()
        self.pulsar_adapter = PulsarStoreAdapter()

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
        elif file_path.startswith('pulsar:'):
            pkg_name = file_path.replace('pulsar:', '', 1)
            return self.pulsar_adapter.install(pkg_name)
        elif file_path.startswith('gnome-ext:') or file_path.startswith('gnome-extension:'):
            prefix = 'gnome-ext:' if file_path.startswith('gnome-ext:') else 'gnome-extension:'
            uuid = file_path.replace(prefix, '', 1)
            return self.get_gnome_extension_install_command(uuid)

        file_extension = os.path.splitext(file_path)[1].lower()
        is_brew_file = HAS_BREW and file_extension == '.rb'
        is_name_only = not file_extension

        # English: Check if it is a supported local package archive (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz, .pkg.tar.gz, .pkg.tar, .pacman)
        # Español: Comprobar si es un archivo de paquete local compatible (.deb, .rpm, .pkg.tar.zst, .pkg.tar.xz, .pkg.tar.gz, .pkg.tar, .pacman)
        is_local_package = (
            file_extension in ('.deb', '.rpm', '.pacman') or
            file_path.lower().endswith('.pkg.tar.zst') or
            file_path.lower().endswith('.pkg.tar.xz') or
            file_path.lower().endswith('.pkg.tar.gz') or
            file_path.lower().endswith('.pkg.tar')
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

    def get_gnome_extension_install_command(self, uuid: str):
        py_script = (
            "import urllib.request, json, subprocess, os, sys, re\n"
            f"uuid = '{uuid}'\n"
            "try:\n"
            "    def get_shell_version():\n"
            "        try:\n"
            "            out = subprocess.check_output(['gnome-shell', '--version']).decode()\n"
            "            m = re.search(r'(\\d+)(?:\\.(\\d+))?', out)\n"
            "            if m: return m.group(1)\n"
            "        except: pass\n"
            "        return '47'\n"
            "    shell_v = get_shell_version()\n"
            "    def parse_ver(v_str):\n"
            "        try:\n"
            "            return tuple(int(p) for p in re.findall(r'\\d+', v_str))\n"
            "        except:\n"
            "            return (0,)\n"
            "    req = urllib.request.Request(f'https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(uuid)}', headers={'User-Agent': 'AppInstall/1.0'})\n"
            "    with urllib.request.urlopen(req, timeout=10) as r:\n"
            "        data = json.loads(r.read().decode('utf-8'))\n"
            "    exts = data.get('extensions', [])\n"
            "    if not exts:\n"
            "        sys.exit(1)\n"
            "    ext = next((e for e in exts if e.get('uuid', '').lower() == uuid.lower() or str(e.get('pk', '')) == str(uuid)), exts[0])\n"
            "    pk = ext.get('pk')\n"
            "    real_uuid = ext.get('uuid', uuid)\n"
            "    info_req = urllib.request.Request(f'https://extensions.gnome.org/extension-info/?pk={pk}', headers={'User-Agent': 'AppInstall/1.0'})\n"
            "    with urllib.request.urlopen(info_req, timeout=10) as r:\n"
            "        info = json.loads(r.read().decode('utf-8'))\n"
            "    shell_map = info.get('shell_version_map', {})\n"
            "    if not shell_map:\n"
            "        sys.exit(1)\n"
            "    sorted_versions = sorted(shell_map.keys(), key=parse_ver)\n"
            "    chosen_tag = shell_map.get(shell_v)\n"
            "    if not chosen_tag:\n"
            "        curr_ver_tuple = parse_ver(shell_v)\n"
            "        compatible = [v for v in sorted_versions if parse_ver(v) <= curr_ver_tuple]\n"
            "        if compatible:\n"
            "            chosen_tag = shell_map[compatible[-1]]\n"
            "        elif sorted_versions:\n"
            "            chosen_tag = shell_map[sorted_versions[-1]]\n"
            "    if not chosen_tag:\n"
            "        sys.exit(1)\n"
            "    tag_pk = chosen_tag.get('pk') if isinstance(chosen_tag, dict) else chosen_tag\n"
            "    dl_url = f'https://extensions.gnome.org/download-extension/{real_uuid}.shell-extension.zip?version_tag={tag_pk}'\n"
            "    tmp_zip = f'/tmp/{real_uuid}.zip'\n"
            "    dl_req = urllib.request.Request(dl_url, headers={'User-Agent': 'AppInstall/1.0'})\n"
            "    with urllib.request.urlopen(dl_req, timeout=20) as r:\n"
            "        with open(tmp_zip, 'wb') as f:\n"
            "            f.write(r.read())\n"
            "    subprocess.run(['gnome-extensions', 'install', '--force', tmp_zip], check=True)\n"
            "    subprocess.run(['gnome-extensions', 'enable', real_uuid], check=False)\n"
            "    if os.path.exists(tmp_zip): os.remove(tmp_zip)\n"
            "    print(f'Extensión {real_uuid} instalada con éxito.')\n"
            "except Exception as e:\n"
            "    print(f'Error al instalar extensión: {e}', file=sys.stderr)\n"
            "    sys.exit(1)\n"
        )
        return ["python3", "-c", py_script]

    def _prepare_env(self):
        # English: Copy current environment and configure privilege escalation to use pkexec (graphical sudo)
        # Español: Copiar el entorno actual y configurar la elevación de privilegios con pkexec (sudo gráfico)
        env = os.environ.copy()
        # English: makepkg must see PACMAN as the plain pacman path; elevation goes in PACMAN_AUTH.
        # If PACMAN contains "pkexec pacman", makepkg resolves it to a broken single path and
        # run_pacman ends up executing: pkexec "/usr/bin/pkexec /usr/bin/pacman" -U ... (double elevation).
        # Español: makepkg debe ver PACMAN como la ruta simple de pacman; la elevación va en PACMAN_AUTH.
        env["SUDO"] = "pkexec"
        env["PACMAN"] = "pacman"
        # makepkg (AUR nativo) usa PACMAN_AUTH para elevar privilegios
        env["PACMAN_AUTH"] = "pkexec"
        # Comandos internos del script de instalación AUR
        env["APPINSTALL_SUDO"] = "pkexec"
        return env

    def _run_process_streaming(self, cmd, on_log):
        """Ejecuta un comando y emite cada línea de salida a on_log."""
        log_lines = []
        env = self._prepare_env()
        process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, bufsize=1
        )
        for line in process.stdout:
            stripped = line.rstrip('\n')
            if stripped.strip():
                log_lines.append(stripped)
                if on_log:
                    GLib.idle_add(on_log, stripped)
        process.wait()
        return process.returncode, "\n".join(log_lines[-50:])

    def run_installation(self, cmd, file_path, on_progress, on_complete, on_log=None):
        def _run():
            try:
                returncode, stderr = self._run_process_streaming(cmd, on_log)
                
                if returncode == 0:
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

    def run_fix_deps(self, cmd, on_progress, on_complete, on_log=None):
        def _run():
            try:
                returncode, stderr = self._run_process_streaming(cmd, on_log)
                
                if returncode == 0:
                    GLib.idle_add(on_complete, _("He arreglado las dependencias"))
                else:
                    GLib.idle_add(on_complete, _("Vaya, un error al corregir dependencias: {}").format(stderr), True)
            except Exception as e:
                GLib.idle_add(on_complete, _("Error al corregir dependencias: {}").format(str(e)), True)

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
