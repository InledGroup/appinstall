import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Gio, Adw

from src.ui.utils import load_css, setup_icon_theme
from src.infrastructure.services.localization import _
from src.infrastructure.adapters.factory import get_package_manager
from src.utils.constants import CURRENT_VERSION
from src.config import CLI_NAME

from src.application.install_service import InstallService
from src.application.update_check_service import UpdateCheckService
from src.application.package_info_service import PackageInfoService
from src.application.search_service import SearchService

# Main Window
def parse_scheme_url(url: str) -> str:
    import urllib.parse
    url = url.strip()
    url_lower = url.lower()
    
    # 1. Pulsar Store schemes & web URLs
    if url_lower.startswith('pulsar-store:') or url_lower.startswith('pulsar:'):
        prefix = 'pulsar-store:' if url_lower.startswith('pulsar-store:') else 'pulsar:'
        rest = url[len(prefix):]
        if rest.startswith('//'):
            rest = rest[2:]
        for p in ['install/', 'package/', 'pkg/', 'show/', 'open/', 'details/']:
            if rest.lower().startswith(p):
                rest = rest[len(p):]
                break
        pkg = rest.split('?')[0].split('#')[0].rstrip('/')
        return f"pulsar:{pkg}"
        
    elif 'store-os.inled.es' in url_lower:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip('/')
        parts = [p for p in path.split('/') if p]
        pkg = None
        for i, p in enumerate(parts):
            if p.lower() in ['pkg', 'package', 'app', 'item'] and i + 1 < len(parts):
                pkg = parts[i + 1]
                break
        if not pkg and parsed.fragment:
            frag_parts = [p for p in parsed.fragment.strip('/').split('/') if p]
            for i, p in enumerate(frag_parts):
                if p.lower() in ['pkg', 'package', 'app', 'item'] and i + 1 < len(frag_parts):
                    pkg = frag_parts[i + 1]
                    break
        if not pkg and parts:
            pkg = parts[-1]
        if pkg:
            return f"pulsar:{pkg}"
            
    # 2. GNOME Extensions schemes & web URLs
    elif url_lower.startswith('gnome-extensions:') or url_lower.startswith('gnome-extension:') or url_lower.startswith('gnome-ext:'):
        if url_lower.startswith('gnome-extensions:'):
            prefix = 'gnome-extensions:'
        elif url_lower.startswith('gnome-extension:'):
            prefix = 'gnome-extension:'
        else:
            prefix = 'gnome-ext:'
        rest = url[len(prefix):]
        if rest.startswith('//'):
            rest = rest[2:]
        for p in ['install/', 'extension/', 'pk/', 'details/']:
            if rest.lower().startswith(p):
                rest = rest[len(p):]
                break
        ext = rest.split('?')[0].split('#')[0].rstrip('/')
        return f"gnome-extension:{ext}"
        
    elif 'extensions.gnome.org' in url_lower:
        parsed = urllib.parse.urlparse(url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        try:
            if 'extension' in parts:
                idx = parts.index('extension')
                if idx + 1 < len(parts):
                    ext_id = parts[idx + 1]
                    return f"gnome-extension:{ext_id}"
        except Exception:
            pass

    # 3. appstream://pkg or appstream:pkg
    elif url_lower.startswith("appstream:"):
        pkg = url[10:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"flatpak:{pkg}"
        
    # 4. Flathub web URLs
    elif 'flathub.org' in url_lower:
        parsed = urllib.parse.urlparse(url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        try:
            if 'apps' in parts:
                idx = parts.index('apps')
                if idx + 1 < len(parts):
                    next_part = parts[idx + 1]
                    if next_part == 'details' and idx + 2 < len(parts):
                        return f"flatpak:{parts[idx + 2]}"
                    else:
                        return f"flatpak:{next_part}"
        except Exception:
            pass

    # 5. snap://pkg or snap:pkg
    elif url_lower.startswith("snap:"):
        pkg = url[5:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"snap:{pkg}"
        
    # 6. flatpak://pkg or flatpak+https://...
    elif url_lower.startswith("flatpak:"):
        pkg = url[8:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"flatpak:{pkg}"
    elif url_lower.startswith("flatpak+https:"):
        return url

    # 7. apt://pkg or apt:pkg
    elif url_lower.startswith("apt:"):
        pkg = url[4:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return pkg
            
    return url


def _resolve_file_arg(raw_arg: str) -> str:
    """Resolve a raw CLI argument into a usable file path or scheme string.
    
    Handles file:// URLs from desktop %U, relative paths, and scheme URLs.
    Returns a resolved path/scheme, or None if not a file/scheme arg.
    """
    from urllib.parse import unquote, urlparse

    arg = raw_arg.strip()
    arg_lower = arg.lower()

    if arg.startswith("file://"):
        try:
            parsed = urlparse(arg)
            arg = unquote(parsed.path)
        except Exception:
            arg = unquote(arg[7:])
        arg_lower = arg.lower()

    if os.path.isfile(arg):
        return os.path.abspath(arg)

    scheme_prefixes = [
        'appstream:', 'snap:', 'flatpak:', 'flatpak+https:',
        'pulsar:', 'pulsar-store:',
        'gnome-extension:', 'gnome-extensions:', 'gnome-ext:',
        'apt:', 'http://', 'https://'
    ]
    if any(arg_lower.startswith(p) for p in scheme_prefixes):
        return parse_scheme_url(arg)

    return None



from src.ui.windows.main_window import PackageInstaller

class AppInstallApp(Adw.Application):
    def __init__(self, file_to_open=None):
        super().__init__(
            application_id="es.inled.AppInstall",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.HANDLES_OPEN
        )
        self.connect("activate", self.on_activate)
        self.connect("command-line", self.on_command_line)
        self.connect("open", self.on_open)
        self.file_to_open = file_to_open

        GLib.set_prgname("es.inled.AppInstall")
        GLib.set_application_name("App Install")
        
        # Initialize core services
        self.pkg_manager = get_package_manager()
        self.install_service = InstallService(self.pkg_manager)
        self.update_service = UpdateCheckService()
        self.info_service = PackageInfoService(self.pkg_manager)
        self.search_service = SearchService(self.pkg_manager)

    def _apply_file_to_window(self):
        """Apply file_to_open to the active window."""
        windows = self.get_windows()
        if not windows:
            return
        win = windows[0]
        win.present()
        if self.file_to_open:
            win.file_path = self.file_to_open
            self.file_to_open = None
            GLib.idle_add(win.load_initial_file)

    def on_command_line(self, app, command_line):
        args = command_line.get_arguments()
        if len(args) > 1 and not self.file_to_open:
            resolved = _resolve_file_arg(args[1])
            if resolved:
                self.file_to_open = resolved
        app.activate()
        return 0

    def on_open(self, app, files, n_files, hint):
        if files and not self.file_to_open:
            raw = files[0].get_path() or files[0].get_uri() or ''
            resolved = _resolve_file_arg(raw)
            if resolved:
                self.file_to_open = resolved
        app.activate()

    def on_activate(self, app):
        windows = app.get_windows()
        if windows:
            self._apply_file_to_window()
            return

        setup_icon_theme()
        load_css()
        
        win = PackageInstaller(
            app, 
            self.install_service, 
            self.update_service, 
            self.pkg_manager, 
            self.info_service,
            search_service=self.search_service,
            file_to_open=self.file_to_open
        )
        if self.file_to_open:
            self.file_to_open = None
        win.present()

def main():
    from src.cli import handle_cli_args, _show_help
    from src.cli_core import COMMANDS

    # No arguments → launch GUI
    if len(sys.argv) < 2:
        app = AppInstallApp()
        return app.run(sys.argv)

    arg = sys.argv[1]
    arg_lower = arg.lower()

    # CLI commands and flags
    if arg_lower in COMMANDS or arg in ('-h', '--help', 'help', '--version', '-V') or arg_lower in ('-h', '--help', 'help', '--version', '-v', 'version', '--uninstall'):
        return handle_cli_args(sys.argv)

    # Resolve file/scheme argument
    resolved = _resolve_file_arg(arg)

    if resolved:
        app = AppInstallApp(file_to_open=resolved)
        return app.run(sys.argv)

    # Unknown argument → show error and help
    print(f"  Unknown command: '{arg}'", file=sys.stderr)
    print(f"  Run '{CLI_NAME} help' for usage.", file=sys.stderr)
    return True

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"Critical error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
