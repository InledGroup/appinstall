import os
import threading
import subprocess
import requests
from gi.repository import Gtk, GLib, Adw
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size, HAS_BREW, BREW_PATH
from src.ui.windows.progress_window import ProgressWindow

class InstalledAppsWindow(Adw.Window):
    def __init__(self, parent, package_manager, uninstall_service):
        super().__init__()
        self.package_manager = package_manager
        self.uninstall_service = uninstall_service
        self.set_title(_("Aplicaciones instaladas"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(500, 400, 0.7)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")
        self.connect("close-request", self._on_close_request)

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Aplicaciones instaladas")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Contenido desplazable para pantallas pequeñas
        if height > 380:
            scrolled_main = Gtk.ScrolledWindow()
            scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled_main.set_propagate_natural_height(True)
            toolbar_view.set_content(scrolled_main)

            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            scrolled_main.set_child(main_box)
        else:
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            toolbar_view.set_content(main_box)

        # Barra de búsqueda con spinner indicador
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_start(8)
        search_box.set_margin_end(8)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Buscar aplicaciones..."))
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.search_entry.add_css_class("search-entry")
        self.search_entry.set_hexpand(True)
        search_box.append(self.search_entry)
        
        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(24, 24)
        search_box.append(self.search_spinner)
        
        main_box.append(search_box)
        
        self.is_loading = False
        self.stop_loading = False

        # Contenedor para el contenido (Stack para manejar estados)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.append(content_box)

        # Separador sutil
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        separator.set_margin_bottom(8)
        content_box.append(separator)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        content_box.append(self.stack)

        # 1. Estado de Carga (Spinner)
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_margin_top(40)
        loading_box.set_margin_bottom(40)
        
        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        loading_box.append(spinner)
        
        self.loading_label = Gtk.Label(label=_("Cargando aplicaciones..."))
        self.loading_label.add_css_class("subtitle-label")
        loading_box.append(self.loading_label)
        
        self.stack.add_named(loading_box, "loading")

        # 2. Estado de Lista (ScrolledWindow + ListBox)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(300)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_filter_func(self.filter_func)
        scrolled_window.set_child(self.listbox)
        
        self.stack.add_named(scrolled_window, "list")

        # 3. Estado "No encontrado"
        no_results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        no_results_box.set_valign(Gtk.Align.CENTER)
        no_results_box.set_halign(Gtk.Align.CENTER)
        no_results_box.set_margin_top(40)
        no_results_box.set_margin_bottom(40)
        
        no_results_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        no_results_icon.set_pixel_size(48)
        no_results_box.append(no_results_icon)
        
        self.no_results_label = Gtk.Label(label=_("No he encontrado nada que coincida"))
        self.no_results_label.add_css_class("title-label")
        no_results_box.append(self.no_results_label)
        
        self.stack.add_named(no_results_box, "empty")
        
        # Barra de progreso para desinstalación
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_bar.set_visible(False)
        main_box.append(self.progress_bar)

        # Mensaje de estado
        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("status-label")
        main_box.append(self.status_label)
        
        # Cargar aplicaciones
        self.load_installed_apps()
    
    def _on_close_request(self, *args):
        self.stop_loading = True
        return False

    def load_installed_apps(self):
        # Ocultar lista para que el borrado sea instantáneo sin re-layouts
        self.listbox.set_visible(False)
        
        # Limpiar la lista actual
        child = self.listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child
        
        self.listbox.set_visible(True)
            
        # Mostrar estado de carga e iniciar spinner de búsqueda
        self.is_loading = True
        self.search_spinner.start()
        self.loading_label.set_text(_("Cargando aplicaciones..."))
        self.stack.set_visible_child_name("loading")
        
        # Iniciar un hilo para cargar las aplicaciones
        thread = threading.Thread(target=self.load_apps_thread)
        thread.daemon = True
        thread.start()
    
    def load_apps_thread(self):
        try:
            # Obtener paquetes instalados
            packages = []
            brew_packages = []
            
            # Obtener paquetes del sistema
            try:
                packages = self.package_manager.list_installed()
            except Exception as e:
                print(f"Error al obtener paquetes: {e}")
            
            # Obtener paquetes de Homebrew
            if HAS_BREW:
                try:
                    output = subprocess.check_output([BREW_PATH, 'list', '--formula'], 
                                                   timeout=15, stderr=subprocess.STDOUT).decode('utf-8')
                    formulas = [line.strip() for line in output.split('\n') if line.strip()]
                    brew_packages.extend(formulas)
                    
                    output_cask = subprocess.check_output([BREW_PATH, 'list', '--cask'], 
                                                        timeout=15, stderr=subprocess.STDOUT).decode('utf-8')
                    casks = [line.strip() for line in output_cask.split('\n') if line.strip()]
                    brew_packages.extend(casks)
                except Exception as e:
                    print(f"Error al obtener paquetes de Homebrew: {e}")

            # Obtener AppImages y PWAs (en system y user local)
            pwas = {} # internal_name -> display_name
            appimages = {} # internal_name -> display_name
            desktop_dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
            
            for desktop_dir in desktop_dirs:
                if os.path.exists(desktop_dir):
                    for filename in os.listdir(desktop_dir):
                        if filename.endswith(".desktop"):
                            desktop_path = os.path.join(desktop_dir, filename)
                            try:
                                with open(desktop_path, 'r') as f:
                                    content = f.read()
                                    app_name = filename.replace(".desktop", "")

                                    import re
                                    name_match = re.search(r'^Name=(.*)$', content, re.MULTILINE)
                                    display_name = name_match.group(1).strip() if name_match else app_name

                                    is_pwa = (
                                        "X-AppInstall=PWA" in content or 
                                        "X-SwiftInstall=PWA" in content or
                                        "--app=" in content or
                                        "--application-mode=" in content
                                    )

                                    if is_pwa:
                                        pwas[app_name] = display_name
                                    else:
                                        is_appinstall_app = (
                                            "X-AppInstall=AppImage" in content or 
                                            "X-SwiftInstall=AppImage" in content or
                                            ("/usr/bin/" in content and "appimage.png" in content) or
                                            (f"Exec=/usr/bin/{app_name}" in content and f"Icon=/usr/share/pixmaps/{app_name}" in content)
                                        )

                                        if is_appinstall_app:
                                            appimages[app_name] = display_name
                            except:
                                pass
            
            # Preparar la lista completa una sola vez
            all_apps = []
            for a_name in sorted(pwas.keys()): all_apps.append((pwas[a_name], a_name, "pwa"))
            for a_name in sorted(appimages.keys()): all_apps.append((appimages[a_name], a_name, "appimage"))
            for b in sorted(brew_packages): all_apps.append((b, b, "brew"))
            for p in sorted(packages): all_apps.append((p, p, "system"))

            # Actualizar la UI en lotes para evitar sobrecargar el bucle principal
            def update_ui_batch(index):
                if getattr(self, "stop_loading", False):
                    return False

                if not all_apps:
                    self.is_loading = False
                    self.search_spinner.stop()
                    self.stack.set_visible_child_name("empty")
                    return False

                if index == 0:
                    self.stack.set_visible_child_name("list")

                batch_size = 50
                end_index = min(index + batch_size, len(all_apps))
                
                for i in range(index, end_index):
                    display_name, internal_name, type = all_apps[i]
                    self.add_app_to_list(display_name, internal_name, type == "appimage", type == "brew", type == "pwa")
                
                if end_index < len(all_apps):
                    GLib.idle_add(lambda: update_ui_batch(end_index))
                else:
                    self.is_loading = False
                    self.search_spinner.stop()
                    self.on_search_changed(self.search_entry)
                
                return False
            
            GLib.idle_add(lambda: update_ui_batch(0))
            
        except Exception as e:
            print(f"Error al cargar aplicaciones: {e}")
            GLib.idle_add(self.show_error_message)
    
    def add_app_to_list(self, display_name, internal_name, is_appimage=False, is_brew=False, is_pwa=False):
        row = Gtk.ListBoxRow()
        row.add_css_class("list-row")
        row.package_name = display_name.lower() # Atributo para filtrado ultra rápido
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        row.set_child(hbox)
        
        if is_appimage:
            icon = Gtk.Image.new_from_icon_name("application-x-executable")
        elif is_pwa:
            icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        elif is_brew:
            brew_logo_path = os.path.expanduser("~/.cache/appinstall/homebrew_logo.png")
            if not os.path.exists(brew_logo_path):
                try:
                    os.makedirs(os.path.dirname(brew_logo_path), exist_ok=True)
                    response = requests.get("https://upload.wikimedia.org/wikipedia/commons/3/34/Homebrew_logo.png", timeout=10)
                    if response.status_code == 200:
                        with open(brew_logo_path, 'wb') as f:
                            f.write(response.content)
                except:
                    pass
            
            if os.path.exists(brew_logo_path):
                icon = Gtk.Image.new_from_file(brew_logo_path)
                icon.set_pixel_size(24)
            else:
                icon = Gtk.Image.new_from_icon_name("system-software-install")
        else:
            icon = Gtk.Image.new_from_icon_name("package-x-generic")
            
        hbox.prepend(icon)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_hexpand(True)
        
        label = Gtk.Label(label=display_name, xalign=0)
        label.add_css_class("title-label")
        vbox.append(label)
        
        if is_appimage:
            type_text = _("AppImage")
        elif is_pwa:
            type_text = _("PWA (Web App)")
        elif is_brew:
            type_text = _("Paquete Homebrew")
        else:
            type_text = _("Paquete del sistema")
            
        type_label = Gtk.Label(label=type_text, xalign=0)
        type_label.add_css_class("subtitle-label")
        vbox.append(type_label)
        
        hbox.append(vbox)
        
        button = Gtk.Button()
        button.set_tooltip_text(_("Desinstalar"))
        button.add_css_class("destructive-button")
        button.set_valign(Gtk.Align.CENTER)
        
        button_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        button.set_child(button_icon)
        
        button.connect("clicked", self.on_uninstall_clicked, internal_name, is_appimage, is_brew, is_pwa)
        hbox.append(button)
        
        self.listbox.append(row)
    
    def show_error_message(self):
        self.is_loading = False
        self.search_spinner.stop()
        
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        
        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        box.append(icon)
        
        label = Gtk.Label(label=_("No he podido encontrar aplicaciones instaladas en tu sistema"))
        label.add_css_class("title-label")
        box.append(label)
        
        row.set_child(box)
        self.listbox.append(row)
        self.stack.set_visible_child_name("list")
        return False
    
    def on_search_changed(self, entry):
        if self.is_loading:
            return
            
        self.search_spinner.start()
        self.listbox.invalidate_filter()
        GLib.idle_add(self.check_filter_results)

    def check_filter_results(self):
        has_visible = False
        child = self.listbox.get_first_child()
        while child:
            if child.is_visible() and child.get_child():
                has_visible = True
                break
            child = child.get_next_sibling()
        
        if not has_visible:
            self.stack.set_visible_child_name("empty")
            self.search_spinner.stop()
        else:
            self.stack.set_visible_child_name("list")
            self.search_spinner.stop()
        return False
    
    def filter_func(self, row):
        text = self.search_entry.get_text().lower()
        if not text:
            return True
        return text in getattr(row, "package_name", "")
    
    def on_uninstall_clicked(self, button, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        if is_appimage:
            message = _("¿Deseas desinstalar {}? (AppImage)").format(package_name)
        elif is_pwa:
            message = _("¿Deseas desinstalar {}? (Web App)").format(package_name)
        elif is_brew:
            message = _("¿Deseas desinstalar {}? (Homebrew)").format(package_name)
        else:
            message = _("¿Deseas desinstalar {}?").format(package_name)
            
        dialog = Adw.AlertDialog(
            heading=_("Confirmación"),
            body=message
        )
        dialog.add_response("no", _("No"))
        dialog.add_response("yes", _("Sí"))
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("no")
        dialog.set_close_response("no")
        
        dialog.choose(self, None, self._on_uninstall_dialog_response, (package_name, is_appimage, is_brew, is_pwa))
    
    def _on_uninstall_dialog_response(self, dialog, result, data):
        package_name, is_appimage, is_brew, is_pwa = data
        try:
            response = dialog.choose_finish(result)
            if response == "yes":
                # Pequeño retardo para dejar que el diálogo de confirmación se cierre suavemente
                GLib.timeout_add(200, lambda: self.uninstall_package(package_name, is_appimage, is_brew, is_pwa))
        except Exception as e:
            print(f"Dialog error: {e}")
    
    def uninstall_package(self, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        # Detener carga si está en curso y desactivar búsqueda para evitar ralentización
        self.stop_loading = True
        self.search_entry.set_sensitive(False)
        self.search_spinner.stop()

        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        self.status_label.set_text(_("Desinstalando {}...").format(package_name))
        
        self.progress_dialog = ProgressWindow(self, _("Desinstalando {}...").format(package_name))
        self.progress_dialog.present()

        cmd = self.uninstall_service.get_uninstall_command(package_name, is_appimage, is_brew, is_pwa, BREW_PATH)
        self.uninstall_service.run_uninstall(cmd, self.update_uninstall_progress, 
                                           lambda success, error: self.uninstall_complete(package_name, success, is_appimage, is_brew, is_pwa, error))
        return False
    
    def update_uninstall_progress(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.05)
        self.progress_bar.set_fraction(new_value)
        return False

    def uninstall_complete(self, package_name, success, is_appimage=False, is_brew=False, is_pwa=False, error_message=None):
        self.search_entry.set_sensitive(True)
        self.stop_loading = False

        # Cerrar el diálogo de progreso primero
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        
        # Esperar un breve momento para que la animación de cierre termine
        GLib.timeout_add(200, self._show_uninstall_result, package_name, success, is_appimage, is_brew, is_pwa, error_message)

    def _show_uninstall_result(self, package_name, success, is_appimage, is_brew, is_pwa, error_message):
        if success:
            if is_appimage:
                message = _("{} ha sido desinstalado correctamente. Recuerda borrar los archivos que haya creado la aplicación.").format(package_name)
            elif is_pwa:
                message = _("La Web App {} ha sido eliminada correctamente.").format(package_name)
            elif is_brew:
                message = _("{} ha sido desinstalado de Homebrew correctamente.").format(package_name)
            else:
                message = _("{} ha sido desinstalado correctamente.").format(package_name)
                
            dialog = Adw.AlertDialog(
                heading=_("Desinstalación completada"),
                body=message
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            self.status_label.set_text(_("Desinstalación completada"))
            
            # Recargar la lista después de que el usuario cierre el aviso
            dialog.connect("response", lambda d, r: self.load_installed_apps())
        else:
            if is_appimage:
                message = _("Error al desinstalar AppImage - {}.").format(package_name)
            elif is_pwa:
                message = _("Error al eliminar la Web App {}.").format(package_name)
            elif is_brew:
                message = _("Error al desinstalar {} de Homebrew.").format(package_name)
            else:
                message = _("Error al desinstalar {}.").format(package_name)
                
            dialog = Adw.AlertDialog(
                heading=_("Error en la desinstalación"),
                body=f"{message}\n\n{error_message or ''}"
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            self.status_label.set_text(_("Uy... ha habido un error cuando estaba desinstalándote la app"))
        
        dialog.present(self)
        return False
