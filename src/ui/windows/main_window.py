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
        # 1. Header Stack (Main Header vs Search Header)
        self.header_stack = Gtk.Stack()
        self.header_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        
        # Main Header
        main_header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="App Install", subtitle=_("Versión {}").format(CURRENT_VERSION))
        main_header.set_title_widget(title_widget)
        main_header.add_css_class("header-bar")
        
        menu_button = Gtk.MenuButton()
        menu_button.set_tooltip_text(_("Menú"))
        menu_button.set_child(Gtk.Image.new_from_icon_name("open-menu-symbolic"))
        
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        popover_box.set_margin_top(10)
        popover_box.set_margin_bottom(10)
        popover_box.set_margin_start(10)
        popover_box.set_margin_end(10)
        for label, callback in [(_("Acerca de App Install"), self.on_about_clicked), 
                                (_("Reportar un error"), self.on_report_issue),
                                (_("Buscar actualizaciones"), self.on_check_updates_clicked)]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            popover_box.append(btn)
        
        popover = Gtk.Popover()
        popover.set_child(popover_box)
        menu_button.set_popover(popover)
        main_header.pack_end(menu_button)
        self.header_stack.add_named(main_header, "main")

        # Search Header
        self.search_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.search_header.add_css_class("header-bar")
        self.search_header.set_margin_top(6)
        self.search_header.set_margin_bottom(6)
        self.search_header.set_margin_start(12)
        self.search_header.set_margin_end(12)
        
        back_btn = Gtk.Button()
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", self.on_search_back_clicked)
        self.search_header.append(back_btn)
        
        self.search_entry_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_entry_container.set_hexpand(True)
        self.search_header.append(self.search_entry_container)
        
        self.header_stack.add_named(self.search_header, "search")

        self.toolbar_view = Adw.ToolbarView()
        self.toolbar_view.add_top_bar(self.header_stack)
        self.set_content(self.toolbar_view)

        # 2. Main Content Stack
        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        self.toolbar_view.set_content(self.main_stack)

        # Main Menu View
        scrolled_main = Gtk.ScrolledWindow()
        scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.main_stack.add_named(scrolled_main, "menu")
        
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.main_box.set_margin_top(24)
        self.main_box.set_margin_bottom(24)
        self.main_box.set_margin_start(24)
        self.main_box.set_margin_end(24)
        scrolled_main.set_child(self.main_box)
        
        # File section
        self.file_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.file_section.add_css_class("card")
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.append(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
        title_label = Gtk.Label(label=_("¿Qué debo instalar?"))
        title_label.add_css_class("title-label")
        title_box.append(title_label)
        self.file_section.append(title_box)
        
        file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        file_chooser_box.add_css_class("file-chooser-button")
        file_chooser_box.append(Gtk.Image.new_from_icon_name("document-open-symbolic"))
        file_label = Gtk.Label(label=_("Selecciona el archivo que debo instalar"))
        file_label.add_css_class("subtitle-label")
        file_chooser_box.append(file_label)
        
        file_btn = Gtk.Button()
        file_btn.set_child(file_chooser_box)
        file_btn.connect("clicked", self.on_file_chooser_clicked)
        self.file_section.append(file_btn)
        
        self.selected_file_label = Gtk.Label(label=_("Aún no has seleccionado ningún archivo"))
        self.selected_file_label.add_css_class("subtitle-label")
        self.file_section.append(self.selected_file_label)
        
        self.entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.entry_box.set_margin_top(8)
        name_label = Gtk.Label(label=_("O escribe el nombre del paquete"), xalign=0)
        name_label.add_css_class("subtitle-label")
        self.entry_box.append(name_label)
        
        self.package_name_entry = Gtk.Entry()
        self.package_name_entry.set_placeholder_text(_("ej: vlc, firefox, chrome..."))
        self.package_name_entry.connect("changed", self.on_package_name_changed)
        self.package_name_entry.connect("activate", lambda e: self.on_install_clicked(None))
        
        # Focus listener
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("enter", self.on_search_focus_enter)
        self.package_name_entry.add_controller(focus_controller)
        
        self.entry_box.append(self.package_name_entry)
        self.file_section.append(self.entry_box)
        self.main_box.append(self.file_section)

        # Actions section
        self.actions_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.actions_section.add_css_class("card")
        
        act_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        act_title_box.append(Gtk.Image.new_from_icon_name("preferences-other-symbolic"))
        act_title_label = Gtk.Label(label=_("Acciones"))
        act_title_label.add_css_class("title-label")
        act_title_box.append(act_title_label)
        self.actions_section.append(act_title_box)
        
        buttons_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box1.set_homogeneous(True)
        self.install_button = self.create_action_button(_("Instalar"), "emblem-system-symbolic", self.on_install_clicked, "action-button")
        self.install_button.set_sensitive(False)
        buttons_box1.append(self.install_button)
        self.fix_deps_button = self.create_action_button(_("Corregir errores"), "applications-utilities-symbolic", self.on_fix_deps_clicked, "secondary-button")
        buttons_box1.append(self.fix_deps_button)
        self.actions_section.append(buttons_box1)

        buttons_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box2.set_homogeneous(True)
        self.apps_button = self.create_action_button(_("Eliminar apps"), "user-trash-symbolic", self.on_apps_clicked, "secondary-button")
        buttons_box2.append(self.apps_button)
        self.clean_button = self.create_action_button(_("Limpiar sistema"), "edit-clear-all-symbolic", self.on_clean_clicked, "secondary-button")
        buttons_box2.append(self.clean_button)
        self.actions_section.append(buttons_box2)

        buttons_box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box3.set_homogeneous(True)
        self.antivirus_button = self.create_action_button(_("Análisis antivirus"), "security-high-symbolic", self.on_antivirus_clicked, "secondary-button")
        buttons_box3.append(self.antivirus_button)
        self.pwa_button = self.create_action_button(_("Crear PWA"), "web-browser-symbolic", self.on_pwa_clicked, "secondary-button")
        buttons_box3.append(self.pwa_button)
        self.actions_section.append(buttons_box3)
        
        self.main_box.append(self.actions_section)
        
        # Progress section
        self.progress_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.progress_section.add_css_class("card")
        prog_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prog_title_box.append(Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic"))
        prog_title_label = Gtk.Label(label=_("Progreso"))
        prog_title_label.add_css_class("title-label")
        prog_title_box.append(prog_title_label)
        self.progress_section.append(prog_title_box)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_section.append(self.progress_bar)
        
        self.status_label = Gtk.Label(label=_("Empieza seleccionando un archivo que contenga una app"))
        self.status_label.add_css_class("status-label")
        self.progress_section.append(self.status_label)
        self.main_box.append(self.progress_section)

        # Search Results View
        results_scrolled = Gtk.ScrolledWindow()
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        results_box.set_margin_top(12)
        results_box.set_margin_bottom(12)
        results_box.set_margin_start(12)
        results_box.set_margin_end(12)
        results_scrolled.set_child(results_box)
        
        self.search_results_list = Gtk.ListBox()
        self.search_results_list.add_css_class("navigation-sidebar")
        self.search_results_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_results_list.connect("row-activated", self.on_search_result_activated)
        results_box.append(self.search_results_list)
        
        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(32, 32)
        self.search_spinner.set_halign(Gtk.Align.CENTER)
        results_box.append(self.search_spinner)
        
        self.main_stack.add_named(results_scrolled, "search_results")
        self.search_timer = None

    def on_search_focus_enter(self, controller):
        if self.header_stack.get_visible_child_name() == "search":
            return
            
        # Mover la entrada al header
        self.entry_box.remove(self.package_name_entry)
        self.search_entry_container.append(self.package_name_entry)
        
        self.header_stack.set_visible_child_name("search")
        self.main_stack.set_visible_child_name("search_results")
        
        # Recuperar foco
        GLib.idle_add(self.package_name_entry.grab_focus)

    def on_search_back_clicked(self, btn):
        # Restaurar entrada a su lugar original
        self.search_entry_container.remove(self.package_name_entry)
        self.entry_box.append(self.package_name_entry)
        
        self.header_stack.set_visible_child_name("main")
        self.main_stack.set_visible_child_name("menu")
        
        self.package_name_entry.set_text("")
        child = self.search_results_list.get_first_child()
        while child:
            self.search_results_list.remove(child)
            child = self.search_results_list.get_first_child()

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
        
        def _search():
            results = []
            try:
                raw_results = self.pkg_manager.search(query)[:15]
                theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                for res in raw_results:
                    if theme.has_icon(res['name']):
                        res['icon'] = res['name']
                    elif theme.has_icon(res['name'].split('-')[0]):
                        res['icon'] = res['name'].split('-')[0]
                    results.append(res)
            except: pass
            
            if HAS_BREW:
                try:
                    brew_output = subprocess.check_output([BREW_PATH, 'search', query], timeout=10, stderr=subprocess.STDOUT).decode('utf-8')
                    for line in brew_output.split('\n')[:15]:
                        if line.strip() and not line.startswith('=='):
                            name = line.strip()
                            results.append({'name': name, 'desc': _("Fórmula de Homebrew"), 'source': 'brew', 'icon': 'system-software-install-symbolic'})
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
            return

        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())

        for res in results:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_all(12)
            
            icon_name = res.get('icon')
            if not icon_name or not theme.has_icon(icon_name):
                icon_name = "package-x-generic-symbolic" if res['source'] == 'apt' else "system-software-install-symbolic"
            
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(32)
            box.append(icon)
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_hexpand(True)
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

    def on_search_result_activated(self, listbox, row):
        pkg_name = row.pkg_name
        if row.source == 'brew':
            pkg_name = f"brew:{pkg_name}"
            
        # Detener cualquier búsqueda en curso para que no se reactive al cambiar el texto
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None
            
        self.package_name_entry.set_text(pkg_name)
        # Mostrar detalles antes de instalar
        self.show_package_details(is_local=False)

    def show_package_details(self, is_local=True):
        identifier = self.file_path if is_local else self.package_name_entry.get_text().strip()
        if not identifier:
            return
            
        self.status_label.set_text(_("Obteniendo información de la aplicación..."))
        self.progress_dialog = ProgressWindow(self, _("Analizando paquete..."))
        self.progress_dialog.present()
        
        def _get_info():
            try:
                info = self.info_service.get_info(identifier, is_local=is_local)
                if is_local:
                    info['ext'] = os.path.splitext(identifier)[1].lstrip('.')
                else:
                    info['ext'] = 'repo'
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
