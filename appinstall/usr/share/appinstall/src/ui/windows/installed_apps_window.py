import os
import threading
import subprocess
import requests
from gi.repository import Gtk, GLib, Adw, Gdk
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size, HAS_BREW, BREW_PATH
from src.ui.windows.progress_window import ProgressWindow

class InstalledAppsWidget(Gtk.Box):
    def __init__(self, parent_window, package_manager, uninstall_service):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.parent_window = parent_window
        self.package_manager = package_manager
        self.uninstall_service = uninstall_service
        self.add_css_class("main-window")
        self.connect("unmap", lambda w: setattr(self, "stop_loading", True))

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)
        header_bar.set_show_start_title_buttons(True)
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Aplicaciones instaladas")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.set_hexpand(True)
        toolbar_view.set_vexpand(True)
        toolbar_view.add_top_bar(header_bar)
        self.append(toolbar_view)

        # Contenedor principal de contenido
        content_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar_view.set_content(content_container)

        # Barra de búsqueda con spinner indicador
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_top(16)
        search_box.set_margin_bottom(8)
        search_box.set_margin_start(16)
        search_box.set_margin_end(16)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Buscar aplicaciones..."))
        self.search_entry.set_key_capture_widget(None)
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.search_entry.add_css_class("search-entry")
        self.search_entry.set_hexpand(True)
        search_box.append(self.search_entry)
        
        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(24, 24)
        search_box.append(self.search_spinner)
        
        content_container.append(search_box)
        
        self.is_loading = False
        self.stop_loading = False

        # Separador sutil
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content_container.append(separator)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        content_container.append(self.stack)

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
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_filter_func(self.filter_func)
        self.listbox.add_css_class("installed-apps-list")
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
        content_container.append(self.progress_bar)

        # Mensaje de estado
        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("status-label")
        content_container.append(self.status_label)
        
        # Cargar aplicaciones
        self.load_installed_apps()
    
    def load_installed_apps(self):
        self.stop_loading = False
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
        """Hilo que carga las aplicaciones de forma incremental para no bloquear la UI."""
        try:
            # Pre-descargar logo de Homebrew en el hilo de fondo (solo una vez)
            if HAS_BREW:
                self.brew_logo_path = os.path.expanduser("~/.cache/appinstall/homebrew_logo.png")
                if not os.path.exists(self.brew_logo_path):
                    try:
                        os.makedirs(os.path.dirname(self.brew_logo_path), exist_ok=True)
                        response = requests.get("https://upload.wikimedia.org/wikipedia/commons/3/34/Homebrew_logo.png", timeout=5)
                        if response.status_code == 200:
                            with open(self.brew_logo_path, 'wb') as f:
                                f.write(response.content)
                    except:
                        self.brew_logo_path = None
            else:
                self.brew_logo_path = None

            # Función auxiliar para enviar lotes a la UI
            def push_to_ui(batch):
                if not getattr(self, "stop_loading", False):
                    GLib.idle_add(self._add_batch_to_list, batch)

            # --- FASE 1: AppImages y PWAs (Lo más rápido y relevante) ---
            desktop_apps = []
            desktop_dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
            
            import re
            name_re = re.compile(r'^Name=(.*)$', re.MULTILINE)
            exec_re = re.compile(r'^Exec=(.*)$', re.MULTILINE)
            icon_re = re.compile(r'^Icon=(.*)$', re.MULTILINE)

            for desktop_dir in desktop_dirs:
                if os.path.exists(desktop_dir):
                    try:
                        for filename in os.listdir(desktop_dir):
                            if getattr(self, "stop_loading", False): break
                            if filename.endswith(".desktop"):
                                desktop_path = os.path.join(desktop_dir, filename)
                                try:
                                    with open(desktop_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read()
                                        app_id = filename.replace(".desktop", "")
                                        name_match = name_re.search(content)
                                        display_name = name_match.group(1).strip() if name_match else app_id
                                        exec_val = exec_re.search(content).group(1).strip() if exec_re.search(content) else ""
                                        icon_val = icon_re.search(content).group(1).strip() if icon_re.search(content) else ""

                                        is_pwa = "X-AppInstall=PWA" in content or "--app=" in exec_val or "--application-mode=" in exec_val
                                        is_appimage = "X-AppInstall=AppImage" in content or "appimage.png" in icon_val or (f"/usr/bin/{app_id}" in exec_val and f"/usr/share/pixmaps/{app_id}" in icon_val)

                                        if is_pwa:
                                            desktop_apps.append((display_name, app_id, False, False, True, False, False, False))
                                        elif is_appimage:
                                            desktop_apps.append((display_name, app_id, True, False, False, False, False, False))
                                except: continue
                    except: pass
            
            if desktop_apps:
                push_to_ui(sorted(desktop_apps))

            # --- FASE 1.5: Flatpak ---
            if not getattr(self, "stop_loading", False):
                try:
                    from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
                    fp = FlatpakAdapter()
                    if fp.is_available():
                        flatpak_batch = []
                        for app_id in fp.list_installed():
                            flatpak_batch.append((app_id, app_id, False, False, False, True, False, False))
                        if flatpak_batch:
                            push_to_ui(sorted(flatpak_batch))
                except Exception as e:
                    print(f"Error loading Flatpaks: {e}")

            # --- FASE 1.6: Snap ---
            if not getattr(self, "stop_loading", False):
                try:
                    from src.infrastructure.adapters.snap_adapter import SnapAdapter
                    sn = SnapAdapter()
                    if sn.is_available():
                        snap_batch = []
                        for snap_name in sn.list_installed():
                            snap_batch.append((snap_name, snap_name, False, False, False, False, True, False))
                        if snap_batch:
                            push_to_ui(sorted(snap_batch))
                except Exception as e:
                    print(f"Error loading Snaps: {e}")

            # --- FASE 2: Homebrew (Suele tardar unos segundos) ---
            if HAS_BREW and not getattr(self, "stop_loading", False):
                try:
                    brew_batch = []
                    output = subprocess.check_output([BREW_PATH, 'list', '--formula'], timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
                    for line in output.split('\n'):
                        if line.strip(): brew_batch.append((line.strip(), line.strip(), False, True, False, False, False, False))
                    
                    output_cask = subprocess.check_output([BREW_PATH, 'list', '--cask'], timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
                    for line in output_cask.split('\n'):
                        if line.strip(): brew_batch.append((line.strip(), line.strip(), False, True, False, False, False, False))
                    
                    if brew_batch:
                        push_to_ui(sorted(brew_batch))
                except: pass

            # --- FASE 3: Paquetes del Sistema & AUR (Pueden ser miles) ---
            if not getattr(self, "stop_loading", False):
                try:
                    import shutil
                    is_pacman = shutil.which('pacman') is not None
                    foreign = set()
                    if is_pacman:
                        try:
                            from src.infrastructure.adapters.aur_adapter import AurAdapter
                            foreign = set(AurAdapter().list_installed())
                        except: pass

                    packages = self.package_manager.list_installed()
                    packages.sort()
                    
                    # Dividir miles de paquetes en lotes pequeños para no saturar el main loop
                    chunk_size = 25
                    for i in range(0, len(packages), chunk_size):
                        if getattr(self, "stop_loading", False): break
                        chunk = packages[i:i + chunk_size]
                        system_batch = []
                        for p in chunk:
                            is_pkg_aur = is_pacman and p in foreign
                            system_batch.append((p, p, False, False, False, False, False, is_pkg_aur))
                        push_to_ui(system_batch)
                        # Dar un pequeño respiro al hilo para que la UI respire
                        import time
                        time.sleep(0.01) 
                except Exception as e:
                    print(f"Error cargando paquetes sistema: {e}")

            # Finalizar carga
            GLib.idle_add(self._finish_loading)

        except Exception as e:
            print(f"Error en load_apps_thread: {e}")
            GLib.idle_add(self.show_error_message)

    def _add_batch_to_list(self, batch):
        """Añade un lote de aplicaciones a la ListBox. Ejecutado en el hilo principal."""
        if getattr(self, "stop_loading", False):
            return False

        if self.stack.get_visible_child_name() == "loading":
            self.stack.set_visible_child_name("list")

        for display_name, internal_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur in batch:
            self.add_app_to_list(display_name, internal_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur)
        
        # Si hay búsqueda activa, necesitamos invalidar el filtro
        if self.search_entry.get_text():
            self.listbox.invalidate_filter()
        
        return False

    def _finish_loading(self):
        """Finaliza el estado de carga en la UI."""
        self.is_loading = False
        self.search_spinner.stop()
        if not self.listbox.get_first_child():
            self.stack.set_visible_child_name("empty")
        return False
    
    def add_app_to_list(self, display_name, internal_name, is_appimage=False, is_brew=False, is_pwa=False, is_flatpak=False, is_snap=False, is_aur=False):
        row = Gtk.ListBoxRow()
        row.add_css_class("list-row")
        row.package_name = display_name.lower() # Atributo para filtrado ultra rápido
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        row.set_child(hbox)
        
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        
        if is_appimage:
            icon = Gtk.Image.new_from_icon_name("application-x-executable")
        elif is_pwa:
            icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        elif is_flatpak:
            icon_name = "flatpak-symbolic" if theme.has_icon("flatpak-symbolic") else "system-software-install"
            icon = Gtk.Image.new_from_icon_name(icon_name)
        elif is_snap:
            icon_name = "snap-symbolic" if theme.has_icon("snap-symbolic") else "system-software-install"
            icon = Gtk.Image.new_from_icon_name(icon_name)
        elif is_aur:
            icon_name = "archlinux-logo" if theme.has_icon("archlinux-logo") else "package-x-generic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
        elif is_brew:
            # Usamos el path pre-calculado en el hilo de fondo
            if hasattr(self, 'brew_logo_path') and self.brew_logo_path and os.path.exists(self.brew_logo_path):
                icon = Gtk.Image.new_from_file(self.brew_logo_path)
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
        elif is_flatpak:
            type_text = _("Flatpak (Flathub)")
        elif is_snap:
            type_text = _("Paquete Snap")
        elif is_aur:
            type_text = _("Paquete AUR")
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
        
        button.connect("clicked", self.on_uninstall_clicked, internal_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur)
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
    
    def on_uninstall_clicked(self, button, package_name, is_appimage=False, is_brew=False, is_pwa=False, is_flatpak=False, is_snap=False, is_aur=False):
        if is_appimage:
            message = _("¿Deseas desinstalar {}? (AppImage)").format(package_name)
        elif is_pwa:
            message = _("¿Deseas desinstalar {}? (Web App)").format(package_name)
        elif is_brew:
            message = _("¿Deseas desinstalar {}? (Homebrew)").format(package_name)
        elif is_flatpak:
            message = _("¿Deseas desinstalar {}? (Flatpak)").format(package_name)
        elif is_snap:
            message = _("¿Deseas desinstalar {}? (Snap)").format(package_name)
        elif is_aur:
            message = _("¿Deseas desinstalar {}? (AUR)").format(package_name)
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
        
        dialog.choose(self.get_root(), None, self._on_uninstall_dialog_response, (package_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur))
    
    def _on_uninstall_dialog_response(self, dialog, result, data):
        package_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur = data
        try:
            response = dialog.choose_finish(result)
            if response == "yes":
                # Pequeño retardo para dejar que el diálogo de confirmación se cierre suavemente
                GLib.timeout_add(200, lambda: self.uninstall_package(package_name, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur))
        except Exception as e:
            print(f"Dialog error: {e}")
    
    def uninstall_package(self, package_name, is_appimage=False, is_brew=False, is_pwa=False, is_flatpak=False, is_snap=False, is_aur=False):
        # Detener carga si está en curso y desactivar búsqueda para evitar ralentización
        self.stop_loading = True
        self.search_entry.set_sensitive(False)
        self.search_spinner.stop()

        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        self.status_label.set_text(_("Desinstalando {}...").format(package_name))
        
        self.progress_dialog = ProgressWindow(self, _("Desinstalando {}...").format(package_name))
        self.progress_dialog.present()

        cmd = self.uninstall_service.get_uninstall_command(
            package_name, is_appimage, is_brew, is_pwa, BREW_PATH,
            is_flatpak=is_flatpak, is_snap=is_snap, is_aur=is_aur
        )
        self.uninstall_service.run_uninstall(cmd, self.update_uninstall_progress, 
                                           lambda success, error: self.uninstall_complete(package_name, success, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur, error))
        return False
    
    def update_uninstall_progress(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.05)
        self.progress_bar.set_fraction(new_value)
        return False

    def uninstall_complete(self, package_name, success, is_appimage=False, is_brew=False, is_pwa=False, is_flatpak=False, is_snap=False, is_aur=False, error_message=None):
        self.search_entry.set_sensitive(True)
        self.stop_loading = False

        # Cerrar el diálogo de progreso primero
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        
        # Esperar un breve momento para que la animación de cierre termine
        GLib.timeout_add(200, self._show_uninstall_result, package_name, success, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur, error_message)

    def _show_uninstall_result(self, package_name, success, is_appimage, is_brew, is_pwa, is_flatpak, is_snap, is_aur, error_message):
        if success:
            if is_appimage:
                message = _("{} ha sido desinstalado correctamente. Recuerda borrar los archivos que haya creado la aplicación.").format(package_name)
            elif is_pwa:
                message = _("La Web App {} ha sido eliminada correctamente.").format(package_name)
            elif is_brew:
                message = _("{} ha sido desinstalado de Homebrew correctamente.").format(package_name)
            elif is_flatpak:
                message = _("{} ha sido desinstalado de Flatpak correctamente.").format(package_name)
            elif is_snap:
                message = _("{} ha sido desinstalado de Snap correctamente.").format(package_name)
            elif is_aur:
                message = _("{} ha sido desinstalado de AUR correctamente.").format(package_name)
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
            elif is_flatpak:
                message = _("Error al desinstalar {} de Flatpak.").format(package_name)
            elif is_snap:
                message = _("Error al desinstalar {} de Snap.").format(package_name)
            elif is_aur:
                message = _("Error al desinstalar {} de AUR.").format(package_name)
            else:
                message = _("Error al desinstalar {}.").format(package_name)
                
            dialog = Adw.AlertDialog(
                heading=_("Error en la desinstalación"),
                body=f"{message}\n\n{error_message or ''}"
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            self.status_label.set_text(_("Uy... ha habido un error cuando estaba desinstalándote la app"))
        
        dialog.present(self.get_root())
        return False
