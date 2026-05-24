import os
import threading
import subprocess
from gi.repository import Gtk, GLib, Adw, Gdk
from src.infrastructure.services.localization import _
from src.utils.constants import CURRENT_VERSION
from src.utils.system import get_safe_window_size, safe_open_url, HAS_BREW, BREW_PATH
from src.ui.components.update_dialog import UpdateDialog

# Import other windows
from .installed_apps_window import InstalledAppsWindow
from .cleanup_window import SystemCleanupWindow
from .antivirus_window import AntivirusWindow
from .pwa_config_window import PWAConfigWindow
from .appimage_config_window import AppImageConfigWindow
from .progress_window import ProgressWindow
from .package_details_window import PackageDetailsWindow

class PackageInstaller(Adw.ApplicationWindow):
    def __init__(self, app, install_service, update_service, pkg_manager, info_service, file_to_open=None):
        super().__init__(application=app)
        self.install_service = install_service
        self.update_service = update_service
        self.pkg_manager = pkg_manager
        self.info_service = info_service
        self.file_path = file_to_open
        
        self.set_title("App Install")
        self.set_icon_name("es.inled.AppInstall")

        width, height = get_safe_window_size(600, 500, 0.9)
        self.set_default_size(width, height)
        self.add_css_class("main-window")
        
        self.setup_ui()
        
        if self.file_path:
            GLib.idle_add(self.load_initial_file)
        
        GLib.timeout_add(500, self.check_updates_on_startup)

    def setup_ui(self):
        # Header bar
        header_bar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="App Install", subtitle=_("Versión {}").format(CURRENT_VERSION))
        header_bar.set_title_widget(title_widget)
        header_bar.add_css_class("header-bar")
        
        # Menu
        menu_button = Gtk.MenuButton()
        menu_button.set_tooltip_text(_("Menú"))
        icon = Gtk.Image.new_from_icon_name("open-menu-symbolic")
        menu_button.set_child(icon)
        
        popover = Gtk.Popover()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        popover_box.set_margin_top(10)
        popover_box.set_margin_bottom(10)
        popover_box.set_margin_start(10)
        popover_box.set_margin_end(10)
        
        about_button = Gtk.Button(label=_("Acerca de App Install"))
        about_button.connect("clicked", self.on_about_clicked)
        popover_box.append(about_button)
        
        report_button = Gtk.Button(label=_("Reportar un error"))
        report_button.connect("clicked", self.on_report_issue)
        popover_box.append(report_button)
        
        update_button = Gtk.Button(label=_("Buscar actualizaciones"))
        update_button.connect("clicked", self.on_check_updates_clicked)
        popover_box.append(update_button)
        
        popover.set_child(popover_box)
        menu_button.set_popover(popover)
        header_bar.pack_end(menu_button)
        
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        toolbar_view.set_content(clamp)

        scrolled_main = Gtk.ScrolledWindow()
        scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_main.set_propagate_natural_height(True)
        clamp.set_child(scrolled_main)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        scrolled_main.set_child(main_box)
        
        # File section
        file_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        file_section.add_css_class("card")
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        title_box.prepend(icon)
        title_label = Gtk.Label(label=_("¿Qué debo instalar?"))
        title_label.add_css_class("title-label")
        title_box.append(title_label)
        file_section.append(title_box)
        
        file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        file_chooser_box.add_css_class("file-chooser-button")
        file_icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
        file_chooser_box.append(file_icon)
        file_label = Gtk.Label(label=_("Selecciona el archivo que debo instalar"))
        file_label.add_css_class("subtitle-label")
        file_chooser_box.append(file_label)
        
        file_chooser_button = Gtk.Button()
        file_chooser_button.set_child(file_chooser_box)
        file_chooser_button.connect("clicked", self.on_file_chooser_clicked)
        file_section.append(file_chooser_button)
        
        self.selected_file_label = Gtk.Label(label=_("Aún no has seleccionado ningún archivo"))
        self.selected_file_label.add_css_class("subtitle-label")
        file_section.append(self.selected_file_label)
        
        name_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_section.set_margin_top(8)
        name_label = Gtk.Label(label=_("O escribe el nombre del paquete"), xalign=0)
        name_label.add_css_class("subtitle-label")
        name_section.append(name_label)
        
        self.package_name_entry = Gtk.Entry()
        self.package_name_entry.set_placeholder_text(_("ej: vlc, firefox, chrome..."))
        self.package_name_entry.connect("changed", self.on_package_name_changed)
        name_section.append(self.package_name_entry)

        self.search_results_scrolled = Gtk.ScrolledWindow()
        self.search_results_scrolled.set_min_content_height(100)
        self.search_results_scrolled.set_max_content_height(300)
        self.search_results_scrolled.set_propagate_natural_height(True)
        self.search_results_scrolled.set_visible(False)
        
        self.search_results_list = Gtk.ListBox()
        self.search_results_list.add_css_class("navigation-sidebar")
        self.search_results_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_results_list.connect("row-activated", self.on_search_result_activated)
        self.search_results_scrolled.set_child(self.search_results_list)
        name_section.append(self.search_results_scrolled)

        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(24, 24)
        self.search_spinner.set_halign(Gtk.Align.CENTER)
        self.search_spinner.set_margin_top(10)
        self.search_spinner.set_visible(False)
        name_section.append(self.search_spinner)

        file_section.append(name_section)
        main_box.append(file_section)

        self.search_timer = None

        # Actions section
        actions_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        actions_section.add_css_class("card")
        
        actions_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions_icon = Gtk.Image.new_from_icon_name("preferences-other-symbolic")
        actions_title_box.prepend(actions_icon)
        actions_title_label = Gtk.Label(label=_("Acciones"))
        actions_title_label.add_css_class("title-label")
        actions_title_box.append(actions_title_label)
        actions_section.append(actions_title_box)
        
        buttons_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box1.set_homogeneous(True)
        
        self.install_button = self.create_action_button(_("Instalar"), "emblem-system-symbolic", self.on_install_clicked, "action-button")
        self.install_button.set_sensitive(False)
        buttons_box1.append(self.install_button)
        
        self.fix_deps_button = self.create_action_button(_("Corregir errores"), "applications-utilities-symbolic", self.on_fix_deps_clicked, "secondary-button")
        buttons_box1.append(self.fix_deps_button)
        actions_section.append(buttons_box1)
        
        buttons_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box2.set_homogeneous(True)
        
        self.apps_button = self.create_action_button(_("Eliminar apps"), "user-trash-symbolic", self.on_apps_clicked, "secondary-button")
        buttons_box2.append(self.apps_button)
        
        self.clean_button = self.create_action_button(_("Limpiar sistema"), "edit-clear-all-symbolic", self.on_clean_clicked, "secondary-button")
        buttons_box2.append(self.clean_button)
        actions_section.append(buttons_box2)
        
        buttons_box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box3.set_homogeneous(True)
        
        self.antivirus_button = self.create_action_button(_("Análisis antivirus"), "security-high-symbolic", self.on_antivirus_clicked, "secondary-button")
        buttons_box3.append(self.antivirus_button)
        
        self.pwa_button = self.create_action_button(_("Crear PWA"), "web-browser-symbolic", self.on_pwa_clicked, "secondary-button")
        buttons_box3.append(self.pwa_button)
        actions_section.append(buttons_box3)
        main_box.append(actions_section)
        
        # Progress section
        progress_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        progress_section.add_css_class("card")
        
        progress_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        progress_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        progress_title_box.prepend(progress_icon)
        progress_title_label = Gtk.Label(label=_("Progreso"))
        progress_title_label.add_css_class("title-label")
        progress_title_box.append(progress_title_label)
        progress_section.append(progress_title_box)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        progress_section.append(self.progress_bar)
        
        self.status_label = Gtk.Label(label=_("Empieza seleccionando un archivo que contenga una app"))
        self.status_label.add_css_class("status-label")
        progress_section.append(self.status_label)
        main_box.append(progress_section)

    def create_action_button(self, label, icon_name, callback, css_class):
        button = Gtk.Button()
        button.add_css_class(css_class)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.prepend(icon)
        label_widget = Gtk.Label(label=label)
        box.append(label_widget)
        button.set_child(box)
        button.connect("clicked", callback)
        return button

    def load_initial_file(self):
        if self.file_path and os.path.exists(self.file_path):
            self.selected_file_label.set_text(_("Archivo seleccionado: {}").format(os.path.basename(self.file_path)))
            self.install_button.set_sensitive(True)
            self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
            # Mostrar detalles automáticamente al cargar archivo inicialmente
            GLib.idle_add(self.show_package_details)
        return False

    def on_file_chooser_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar paquete"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        dialog.connect("response", self._on_file_dialog_response)
        dialog.show()

    def _on_file_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.file_path = file.get_path()
                self.selected_file_label.set_text(_("Archivo seleccionado: {}").format(os.path.basename(self.file_path)))
                self.install_button.set_sensitive(True)
                self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
                self.package_name_entry.set_text("")
                self.search_results_scrolled.set_visible(False)
                # Mostrar detalles al seleccionar archivo
                self.show_package_details()
        dialog.destroy()

    def show_package_details(self):
        if not self.file_path or not os.path.exists(self.file_path):
            return
            
        self.status_label.set_text(_("Obteniendo información de la aplicación..."))
        self.progress_dialog = ProgressWindow(self, _("Analizando paquete..."))
        self.progress_dialog.present()
        
        def _get_info():
            try:
                info = self.info_service.get_info(self.file_path)
                info['ext'] = os.path.splitext(self.file_path)[1].lstrip('.')
                GLib.idle_add(self._present_details_window, info)
            except Exception as e:
                print(f"Error getting package info: {e}")
                GLib.idle_add(self._hide_progress_and_error)
            
        threading.Thread(target=_get_info, daemon=True).start()

    def _hide_progress_and_error(self):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        self.status_label.set_text(_("No he podido obtener detalles del paquete"))

    def _present_details_window(self, info):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.status_label.set_text(_("Detalles de la aplicación cargados"))
        details_win = PackageDetailsWindow(self, info, lambda: self.on_install_clicked(None))
        details_win.present()

    def on_install_clicked(self, widget):
        if not self.file_path:
            package_name = self.package_name_entry.get_text().strip()
            if package_name:
                self.file_path = package_name
            else:
                return
        
        # Determine command using InstallService
        ext_lower = ""
        if os.path.exists(self.file_path):
            ext_lower = os.path.splitext(self.file_path)[1].lower()
        
        if ext_lower == '.appimage':
            config_window = AppImageConfigWindow(self, self.file_path, self.proceed_with_appimage_installation)
            config_window.present()
            return
        
        cmd = self.install_service.get_install_command(self.file_path)
        if not cmd:
            self.status_label.set_text(_("Formato de paquete no soportado por App Install"))
            return

        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)
        
        self.progress_dialog = ProgressWindow(self, _("Instalando..."))
        self.progress_dialog.present()
        
        self.install_service.run_installation(cmd, self.file_path, self.update_progress_ui, self.on_installation_complete)

    def on_fix_deps_clicked(self, widget):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Corrigiendo errores"))
        self.progress_bar.set_fraction(0.0)
        
        self.progress_dialog = ProgressWindow(self, _("Corrigiendo errores"))
        self.progress_dialog.present()
        
        cmd = self.pkg_manager.fix_broken()
        self.install_service.run_fix_deps(cmd, self.update_progress_ui, self.on_fix_deps_complete)

    def on_apps_clicked(self, widget):
        from src.application.uninstall_service import UninstallService
        uninstall_service = UninstallService(self.pkg_manager)
        apps_window = InstalledAppsWindow(self, self.pkg_manager, uninstall_service)
        apps_window.present()

    def on_clean_clicked(self, widget):
        from src.application.cleanup_service import CleanupService
        cleanup_service = CleanupService(self.pkg_manager)
        clean_window = SystemCleanupWindow(self, cleanup_service)
        clean_window.present()

    def on_antivirus_clicked(self, widget):
        from src.application.antivirus_service import AntivirusService
        antivirus_service = AntivirusService(self.pkg_manager)
        antivirus_window = AntivirusWindow(self, antivirus_service)
        antivirus_window.present()

    def on_pwa_clicked(self, widget):
        pwa_window = PWAConfigWindow(self, self.proceed_with_pwa_installation)
        pwa_window.present()

    def proceed_with_appimage_installation(self, display_name, icon_path):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)
        
        self.progress_dialog = ProgressWindow(self, _("Instalando {}...").format(display_name))
        self.progress_dialog.present()
        
        cmd = self.install_service.get_appimage_install_command(self.file_path, display_name, icon_path)
        self.install_service.run_installation(cmd, self.file_path, self.update_progress_ui, self.on_installation_complete)

    def proceed_with_pwa_installation(self, display_name, url, icon_path):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Creando PWA..."))
        self.progress_bar.set_fraction(0.0)
        
        self.progress_dialog = ProgressWindow(self, _("Creando PWA {}...").format(display_name))
        self.progress_dialog.present()
        
        cmd = self.install_service.get_pwa_install_command(display_name, url, icon_path)
        self.install_service.run_installation(cmd, None, self.update_progress_ui, self.on_installation_complete)

    def update_progress_ui(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.01)
        self.progress_bar.set_fraction(new_value)
        return False

    def on_installation_complete(self, message, is_error=False, stderr_output=""):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        
        if is_error:
            # Handle missing dependencies if needed (omitted for brevity here, should be in InstallService)
            dialog = Adw.AlertDialog(heading=_("¡Un error en la instalación!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He terminado la instalación"), body=message)
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)
        self.set_buttons_sensitive(True)

    def on_fix_deps_complete(self, message, is_error=False):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error al corregir las dependencias!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He corregido las dependencias"), body=message)
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)
        self.set_buttons_sensitive(True)

    def set_buttons_sensitive(self, sensitive):
        self.install_button.set_sensitive(sensitive)
        self.fix_deps_button.set_sensitive(sensitive)
        self.apps_button.set_sensitive(sensitive)
        self.clean_button.set_sensitive(sensitive)
        self.antivirus_button.set_sensitive(sensitive)
        self.pwa_button.set_sensitive(sensitive)

    def check_updates_on_startup(self):
        thread = threading.Thread(target=self.check_updates_thread)
        thread.daemon = True
        thread.start()
        return False

    def check_updates_thread(self):
        update_info = self.update_service.check_for_updates()
        if update_info:
            has_update, latest_version, release_url = update_info
            if has_update:
                GLib.idle_add(self.show_update_dialog, latest_version, release_url)

    def show_update_dialog(self, latest_version, release_url):
        dialog = UpdateDialog(self, latest_version, release_url)
        dialog.choose(self, None, self._on_update_dialog_response, release_url)
        return False

    def _on_update_dialog_response(self, dialog, result, release_url):
        try:
            response = dialog.choose_finish(result)
            if response == "update":
                safe_open_url(release_url)
        except Exception as e:
            print(f"Dialog error: {e}")

    def on_check_updates_clicked(self, widget):
        self.status_label.set_text(_("Estoy comprobando las actualizaciones"))
        def _check():
            update_info = self.update_service.check_for_updates()
            if update_info:
                has_update, latest_version, release_url = update_info
                if has_update:
                    GLib.idle_add(self.show_update_dialog, latest_version, release_url)
                else:
                    GLib.idle_add(self.show_no_updates_message)
            else:
                GLib.idle_add(self.show_update_check_error)
        
        thread = threading.Thread(target=_check)
        thread.daemon = True
        thread.start()

    def show_no_updates_message(self):
        dialog = Adw.AlertDialog(
            heading=_("Estoy actualizado :)"),
            body=_("Bien hecho, estoy actualizado a la última versión ({}).").format(CURRENT_VERSION)
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        return False

    def show_update_check_error(self):
        dialog = Adw.AlertDialog(
            heading=_("He encontrado un error"),
            body=_("Vaya, no he podido comprobar las actualizaciones. ¿Estás conectado a internet?")
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        return False

    def on_package_name_changed(self, entry):
        text = entry.get_text().strip()
        if text:
            if self.file_path:
                self.file_path = None
                self.selected_file_label.set_text(_("Aún no has seleccionado ningún archivo"))
            self.install_button.set_sensitive(True)
        elif not self.file_path:
            self.install_button.set_sensitive(False)

        if self.search_timer:
            GLib.source_remove(self.search_timer)
        if len(text) >= 3:
            self.search_timer = GLib.timeout_add(500, self.perform_package_search, text)
        else:
            self.search_results_scrolled.set_visible(False)

    def perform_package_search(self, query):
        self.search_spinner.set_visible(True)
        self.search_spinner.start()
        self.search_results_scrolled.set_visible(False)
        
        def _search():
            results = []
            try:
                results.extend(self.pkg_manager.search(query)[:15])
            except: pass
            
            if HAS_BREW:
                try:
                    brew_output = subprocess.check_output([BREW_PATH, 'search', query], timeout=10, stderr=subprocess.STDOUT).decode('utf-8')
                    for line in brew_output.split('\n')[:15]:
                        if line.strip() and not line.startswith('=='):
                            results.append({'name': line.strip(), 'desc': _("Fórmula de Homebrew"), 'source': 'brew'})
                except: pass
            GLib.idle_add(self.show_search_results, results)
            
        threading.Thread(target=_search, daemon=True).start()
        return False

    def show_search_results(self, results):
        self.search_spinner.stop()
        self.search_spinner.set_visible(False)
        child = self.search_results_list.get_first_child()
        while child:
            self.search_results_list.remove(child)
            child = self.search_results_list.get_first_child()

        if not results:
            self.search_results_scrolled.set_visible(False)
            return

        for res in results:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(12)
            box.set_margin_end(12)
            
            icon_name = "package-x-generic-symbolic" if res['source'] == 'apt' else "system-software-install-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_opacity(0.7)
            box.append(icon)
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            name_label = Gtk.Label(label=res['name'], xalign=0)
            name_label.add_css_class("title-label") 
            vbox.append(name_label)
            
            desc_label = Gtk.Label(label=res['desc'], xalign=0)
            desc_label.set_ellipsize(3)
            desc_label.add_css_class("subtitle-label")
            vbox.append(desc_label)
            
            box.append(vbox)
            row.set_child(box)
            row.pkg_name = res['name']
            row.source = res['source']
            self.search_results_list.append(row)
        
        self.search_results_scrolled.set_visible(True)

    def on_search_result_activated(self, listbox, row):
        pkg_name = row.pkg_name
        if row.source == 'brew':
            pkg_name = f"brew:{pkg_name}"
            
        # Detener cualquier búsqueda en curso para que no se reactive al cambiar el texto
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None
            
        self.package_name_entry.set_text(pkg_name)
        self.search_results_scrolled.set_visible(False)
        self.search_spinner.set_visible(False)
        self.install_button.set_sensitive(True)
        
        # Lanzar la instalación directamente
        self.on_install_clicked(None)

    def on_about_clicked(self, widget):
        about_dialog = Adw.AboutWindow(
            transient_for=self,
            modal=True,
            application_name="App Install",
            application_icon="es.inled.AppInstall",
            version=CURRENT_VERSION,
            comments=_("Instalador de paquetes gráfico para Linux."),
            copyright="© 2026 Inled Group",
            website="https://license.inled.es",
            developers=["Inled Group"]
        )
        about_dialog.present()

    def on_report_issue(self, widget):
        safe_open_url("https://github.com/InledGroup/appinstall/issues")
