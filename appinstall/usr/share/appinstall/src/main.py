import sys
import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Gio, Adw

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ui.utils import load_css, setup_icon_theme
from src.infrastructure.services.localization import _
from src.infrastructure.adapters.factory import get_package_manager
from src.utils.constants import CURRENT_VERSION

# Services
from src.application.install_service import InstallService
from src.application.update_check_service import UpdateCheckService
from src.application.package_info_service import PackageInfoService
from src.application.search_service import SearchService

# Main Window
def parse_scheme_url(url: str) -> str:
    url_lower = url.lower()
    
    # 1. appstream://pkg or appstream:pkg
    if url_lower.startswith("appstream:"):
        pkg = url[10:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"flatpak:{pkg}"
        
    # 2. snap://pkg or snap:pkg
    elif url_lower.startswith("snap:"):
        pkg = url[5:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"snap:{pkg}"
        
    # 3. flatpak://pkg or flatpak:pkg or flatpak+https://...
    elif url_lower.startswith("flatpak:"):
        pkg = url[8:]
        if pkg.startswith("//"):
            pkg = pkg[2:]
        pkg = pkg.split("?")[0].split("/")[0]
        return f"flatpak:{pkg}"
    elif url_lower.startswith("flatpak+https:"):
        return url
        
    # 4. https://flathub.org/apps/details/org.gimp.GIMP or similar
    elif url_lower.startswith("https://flathub.org/apps/") or url_lower.startswith("http://flathub.org/apps/"):
        parts = url.split("?")[0].split("/")
        try:
            apps_idx = parts.index("apps")
            if apps_idx + 1 < len(parts):
                next_part = parts[apps_idx + 1]
                if next_part == "details" and apps_idx + 2 < len(parts):
                    return f"flatpak:{parts[apps_idx + 2]}"
                else:
                    return f"flatpak:{next_part}"
        except ValueError:
            pass
            
    return url

from src.ui.windows.main_window import PackageInstaller

class AppInstallApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="es.inled.AppInstall", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.connect("activate", self.on_activate)
        self.connect("command-line", self.on_command_line)
        self.file_to_open = None

        GLib.set_prgname("es.inled.AppInstall")
        GLib.set_application_name("App Install")
        
        # Initialize core services
        self.pkg_manager = get_package_manager()
        self.install_service = InstallService(self.pkg_manager)
        self.update_service = UpdateCheckService()
        self.info_service = PackageInfoService(self.pkg_manager)
        self.search_service = SearchService(self.pkg_manager)

    def on_command_line(self, app, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            file_path = args[1]
            is_scheme = any(file_path.lower().startswith(prefix) for prefix in ["appstream:", "snap:", "flatpak:", "flatpak+https:", "http://", "https://"])
            if is_scheme:
                self.file_to_open = parse_scheme_url(file_path)
            else:
                if not os.path.isabs(file_path):
                    cwd = command_line.get_cwd()
                    file_path = os.path.join(cwd, file_path)
                self.file_to_open = file_path

        app.activate()
        return 0

    def on_activate(self, app):
        windows = app.get_windows()
        if windows:
            windows[0].present()
            if self.file_to_open:
                windows[0].file_path = self.file_to_open
                windows[0].load_initial_file()
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
        win.present()

def main():
    app = AppInstallApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"Critical error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
