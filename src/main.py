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

# Main Window
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

    def on_command_line(self, app, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            file_path = args[1]
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
