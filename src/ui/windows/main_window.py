import os
import json
import threading
import subprocess
import requests
from gi.repository import Gtk, GLib, Adw, Gdk, Pango
from src.infrastructure.services.localization import _
from src.utils.constants import CURRENT_VERSION
from src.utils.system import get_safe_window_size, safe_open_url, has_internet, HAS_BREW, BREW_PATH, open_google_ai_mode, analyze_pkgbuild_with_ai
from src.application import prompt_engine
from src.application.recommendations_service import RecommendationsService
from src.utils.terminal import open_last_failure_in_terminal
from src.ui.components.update_dialog import UpdateDialog
from src.ui.components.operation_bar import OperationBar

# Import other windows
from .installed_apps_window import InstalledAppsWidget
from .cleanup_window import SystemCleanupWidget
from .antivirus_window import AntivirusWidget
from .pwa_config_window import PWAConfigWindow
from .appimage_config_window import AppImageConfigWindow
from .progress_window import ProgressWindow
from .package_details_window import PackageDetailsWidget
from .pulsar_store_window import PulsarStoreWidget
from .gnome_extensions_window import GnomeExtensionsWidget, is_gnome_desktop

class ScrollingTextContainer(Gtk.ScrolledWindow):
    def __init__(self, text, label_class):
        super().__init__()
        self.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.set_hexpand(True)
        self.add_css_class("scrolling-text-container")
        
        self.text = text
        self.label_class = label_class
        
        # We use a single Gtk.Box as child at all times to prevent C-object garbage collection segfaults!
        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=32)
        
        self.lbl1 = Gtk.Label(label=text, xalign=0)
        self.lbl1.add_css_class(label_class)
        self.lbl1.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl1.set_wrap(False)
        self.hbox.append(self.lbl1)
        
        self.lbl2 = Gtk.Label(label=text, xalign=0)
        self.lbl2.add_css_class(label_class)
        self.lbl2.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.lbl2.set_wrap(False)
        self.lbl2.set_visible(False) # Hidden by default
        self.hbox.append(self.lbl2)
        
        self.set_child(self.hbox)
        
        self.scroll_timer_id = 0
        self.current_offset = 0
        
    def start_scrolling(self):
        # Disable ellipsize on lbl1 to measure its full width and allow scrolling
        self.lbl1.set_ellipsize(Pango.EllipsizeMode.NONE)
        
        def init_scroll():
            hadj = self.get_hadjustment()
            w = self.lbl1.get_width()
            spacing = 32
            period = w + spacing
            
            viewport_width = self.get_width()
            if w <= viewport_width:
                # Text fits inside, no marquee scrolling needed!
                self.lbl1.set_ellipsize(Pango.EllipsizeMode.END)
                return False
                
            # Make the wrap-around label visible
            self.lbl2.set_visible(True)
            self.current_offset = 0
            
            def scroll_step():
                nonlocal period
                if period <= 32:
                    period = self.lbl1.get_width() + 32
                    if period <= 32:
                        return True
                        
                self.current_offset += 1.0
                if self.current_offset >= period:
                    self.current_offset = 0
                    
                hadj.set_value(self.current_offset)
                return True
                
            self.scroll_timer_id = GLib.timeout_add(30, scroll_step)
            return False
            
        GLib.timeout_add(100, init_scroll)
        
    def stop_scrolling(self):
        if self.scroll_timer_id > 0:
            GLib.source_remove(self.scroll_timer_id)
            self.scroll_timer_id = 0
        self.lbl2.set_visible(False)
        self.lbl1.set_ellipsize(Pango.EllipsizeMode.END)
        hadj = self.get_hadjustment()
        hadj.set_value(0)
        self.current_offset = 0

class PackageInstaller(Adw.ApplicationWindow):
    def __init__(self, app, install_service, update_service, pkg_manager, info_service, search_service=None, file_to_open=None):
        super().__init__(application=app)
        self.install_service = install_service
        self.update_service = update_service
        self.pkg_manager = pkg_manager
        self.info_service = info_service
        self.search_service = search_service
        # Recomendaciones curadas del inicio (recommendations.json del repo)
        self.recommendations_service = RecommendationsService()
        # Hilo del ciclo de actualizaciones automáticas (si está activado)
        self._auto_update_thread = None
        # Identificador de la operación de comprobación de actualizaciones
        self._updates_check_op_id = None
        self.file_path = file_to_open

        # English: Any package manager question asked during an operation is
        # answered here with a two-button popup (see prompt_engine)
        # Español: Cualquier pregunta del gestor de paquetes durante una
        # operación se responde aquí con un popup de dos botones (ver prompt_engine)
        prompt_engine.set_prompt_handler(self._answer_package_question)

        self.set_title("App Install")
        self.set_icon_name("es.inled.AppInstall")

        # English: Identifier of the most recently started operation
        # Español: Identificador de la última operación iniciada
        self._last_operation_id = None

        width, height = get_safe_window_size(950, 650, 0.95)
        self.set_default_size(width, height)
        self.add_css_class("main-window")
        
        self.setup_ui()
        
        if self.file_path:
            GLib.idle_add(self.load_initial_file)
        
        GLib.timeout_add(500, self.check_updates_on_startup)

    def setup_ui(self):
        # 1. Main outer layout container: Gtk.Box (Horizontal)
        main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # English: Toast overlay to show short messages (e.g. the browser
        # window that was just opened) without stealing the focus.
        # Español: Capa de avisos para mostrar mensajes breves (por ejemplo la
        # ventana del navegador que se acaba de abrir) sin robar el foco.
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(main_layout)
        self.set_content(self.toast_overlay)

        # --- Sidebar (Left Pane) ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        sidebar_box.set_size_request(240, -1)
        sidebar_box.add_css_class("sidebar-container")
        
        # Header with App branding
        branding_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        branding_box.set_margin_top(16)
        branding_box.set_margin_bottom(8)
        branding_box.set_margin_start(16)
        branding_box.set_margin_end(16)
        
        app_icon = Gtk.Image.new_from_icon_name("es.inled.AppInstall")
        app_icon.set_pixel_size(32)
        branding_box.append(app_icon)
        
        app_title = Gtk.Label(label="App Install", xalign=0)
        app_title.add_css_class("title-label")
        branding_box.append(app_title)
        
        sidebar_box.append(branding_box)
        
        # Search Entry in Sidebar (App Store style)
        self.sidebar_search_entry = Gtk.SearchEntry()
        self.sidebar_search_entry.set_placeholder_text(_("Buscar..."))
        self.sidebar_search_entry.add_css_class("sidebar-search")
        self.sidebar_search_entry.set_margin_start(12)
        self.sidebar_search_entry.set_margin_end(12)
        self.sidebar_search_entry.connect("search-changed", self.on_sidebar_search_changed)
        self.sidebar_search_entry.connect("activate", self.on_sidebar_search_activated)
        sidebar_box.append(self.sidebar_search_entry)
        
        # Navigation ListBox
        self.sidebar_list = Gtk.ListBox()
        self.sidebar_list.add_css_class("navigation-sidebar")
        self.sidebar_list.set_margin_start(8)
        self.sidebar_list.set_margin_end(8)
        self.sidebar_list.connect("row-activated", self.on_sidebar_row_activated)
        
        # Add Navigation Rows
        self.add_sidebar_row(self.sidebar_list, "store", _("Buscar / Tienda"), "system-search-symbolic")
        
        pulsar_store_icon = "emblem-favorite-symbolic"
        for icon_cand in [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "pulsar-store.svg"),
            "/usr/share/icons/hicolor/scalable/apps/pulsar-store.svg"
        ]:
            if os.path.exists(icon_cand):
                pulsar_store_icon = icon_cand
                break
        self.add_sidebar_row(self.sidebar_list, "pulsar_store", _("Pulsar Store"), pulsar_store_icon)
        
        if is_gnome_desktop():
            self.add_sidebar_row(self.sidebar_list, "gnome_extensions", _("Extensiones GNOME"), "application-x-addon-symbolic")
        self.add_sidebar_row(self.sidebar_list, "installed", _("Mis Aplicaciones"), "system-software-install-symbolic")
        self.add_sidebar_row(self.sidebar_list, "updates", _("Actualizaciones"), "software-update-available-symbolic")
        self.add_sidebar_row(self.sidebar_list, "cleanup", _("Limpiar Sistema"), "user-trash-symbolic")
        self.add_sidebar_row(self.sidebar_list, "antivirus", _("Análisis de Virus"), "security-high-symbolic")
        
        sidebar_box.append(self.sidebar_list)
        main_layout.append(sidebar_box)
        
        # Separator line
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_layout.append(sep)

        # --- Content Area (Right Pane) ---
        content_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_wrapper.set_hexpand(True)
        content_wrapper.set_vexpand(True)

        self.content_stack = Adw.ViewStack()
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)
        content_wrapper.append(self.content_stack)

        # --- Bottom Progress & Activity Bar ---
        # English: One row per running operation, so concurrent processes get
        # their own progress bar and never cancel each other out.
        # Español: Una fila por operación en curso, así los procesos
        # concurrentes tienen su propia barra y no se anulan entre sí.
        self.operation_bar = OperationBar()
        content_wrapper.append(self.operation_bar)
        # Alias histórico: otras ventanas siguen usando este atributo
        self.bottom_progress_box = self.operation_bar
        main_layout.append(content_wrapper)

        # Create original store content (Header Stack + ToolbarView + main_stack)
        store_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Header Stack
        self.header_stack = Gtk.Stack()
        self.header_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        
        # --- Main Header ---
        main_header = Adw.HeaderBar()
        main_header.set_show_end_title_buttons(True)
        main_header.set_show_start_title_buttons(True)
        title_widget = Adw.WindowTitle(title="App Install", subtitle=_("Versión {}").format(CURRENT_VERSION))
        main_header.set_title_widget(title_widget)
        main_header.add_css_class("header-bar")
        
        menu_button = Gtk.MenuButton()
        menu_button.set_tooltip_text(_("Menú"))
        menu_button.set_child(Gtk.Image.new_from_icon_name("open-menu-symbolic"))
        
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        popover_box.set_margin_top(10); popover_box.set_margin_bottom(10)
        popover_box.set_margin_start(10); popover_box.set_margin_end(10)
        
        for label, callback in [(_("Acerca de App Install"), self.on_about_clicked), 
                                (_("Reportar un error"), self.on_report_issue),
                                (_("Buscar actualizaciones"), self.on_check_updates_clicked),
                                (_("Prioridad de búsqueda..."), self.on_search_priority_clicked)]:
            btn = Gtk.Button(label=label); btn.connect("clicked", callback)
            popover_box.append(btn)
        
        popover = Gtk.Popover(); popover.set_child(popover_box)
        self.menu_popover = popover
        menu_button.set_popover(popover)
        main_header.pack_end(menu_button)
        self.header_stack.add_named(main_header, "main")

        # --- Search Header ---
        self.search_header_bar = Adw.HeaderBar()
        self.search_header_bar.set_show_end_title_buttons(True)
        self.search_header_bar.set_show_start_title_buttons(True)
        self.search_header_bar.add_css_class("header-bar")
        
        search_header_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        search_header_content.set_hexpand(True)
        
        back_btn = Gtk.Button()
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", self.on_search_back_clicked)
        search_header_content.append(back_btn)
        
        # Just a Title Label instead of a search entry
        search_title_label = Gtk.Label(label=_("Resultados de búsqueda"))
        search_title_label.add_css_class("title-label")
        search_header_content.append(search_title_label)
        
        self.search_header_bar.set_title_widget(search_header_content)
        self.header_stack.add_named(self.search_header_bar, "search")

        # --- Details Header (toolbar with close button and back) ---
        self.details_header_bar = Adw.HeaderBar()
        self.details_header_bar.set_show_end_title_buttons(True)
        self.details_header_bar.set_show_start_title_buttons(False)
        self.details_header_bar.add_css_class("header-bar")

        details_back_btn = Gtk.Button()
        details_back_btn.set_icon_name("go-previous-symbolic")
        details_back_btn.add_css_class("flat")
        details_back_btn.connect("clicked", self.on_details_back_clicked)
        self.details_header_bar.pack_start(details_back_btn)

        self.details_title_label = Gtk.Label(label="", xalign=0)
        self.details_title_label.add_css_class("title-label")
        self.details_header_bar.set_title_widget(self.details_title_label)

        self.header_stack.add_named(self.details_header_bar, "details")

        store_box.append(self.header_stack)
        
        # original main_stack
        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.main_stack.set_hexpand(True)
        self.main_stack.set_vexpand(True)
        store_box.append(self.main_stack)
        
        self.content_stack.add_named(store_box, "store")

        # Create original store menus
        self.setup_store_menus()

        # Initialize embedded widgets
        from src.application.uninstall_service import UninstallService
        from src.application.cleanup_service import CleanupService
        from src.application.antivirus_service import AntivirusService

        # 1. Pulsar Store Widget
        self.pulsar_store_widget = PulsarStoreWidget(self)
        self.content_stack.add_named(self.pulsar_store_widget, "pulsar_store")

        # 2. GNOME Extensions Widget (if available)
        if is_gnome_desktop():
            self.gnome_extensions_widget = GnomeExtensionsWidget(self)
            self.content_stack.add_named(self.gnome_extensions_widget, "gnome_extensions")

        # 3. Installed Apps Widget
        uninstall_service = UninstallService(self.pkg_manager)
        self.installed_apps_widget = InstalledAppsWidget(self, self.pkg_manager, uninstall_service)
        self.content_stack.add_named(self.installed_apps_widget, "installed")

        # 4. Updates Widget
        self.updates_widget = self.setup_updates_widget()
        self.content_stack.add_named(self.updates_widget, "updates")

        # Si las actualizaciones automáticas están activadas, arrancar el ciclo
        # en segundo plano (solo si no lo está haciendo ya el demonio de sesión,
        # gracias al bloqueo de instancia única del DaemonService).
        if self._load_auto_update():
            GLib.timeout_add_seconds(5, self._ensure_auto_update_loop)

        # 5. Cleanup Widget
        cleanup_service = CleanupService(self.pkg_manager)
        self.cleanup_widget = SystemCleanupWidget(self, cleanup_service)
        self.content_stack.add_named(self.cleanup_widget, "cleanup")

        # 6. Antivirus Widget
        antivirus_service = AntivirusService(self.pkg_manager)
        self.antivirus_widget = AntivirusWidget(self, antivirus_service)
        self.content_stack.add_named(self.antivirus_widget, "antivirus")

        # Ensure termination
        self.connect("close-request", self._on_close_request)

        # Select first row
        GLib.idle_add(lambda: self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0)))

    def add_sidebar_row(self, listbox, target_page, label_text, icon_name):
        row = Gtk.ListBoxRow()
        row.target_page = target_page
        row.add_css_class("sidebar-row")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        if icon_name.endswith(".svg") or icon_name.endswith(".png") or os.path.exists(icon_name):
            icon = Gtk.Image.new_from_file(icon_name)
        else:
            icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
        box.append(icon)
        
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_hexpand(True)
        box.append(label)
        
        row.set_child(box)
        listbox.append(row)

    def on_sidebar_row_activated(self, listbox, row):
        if not row:
            return
        target = row.target_page
        
        # Reset store search state if switching away from store
        if target != "store":
            self.header_stack.set_visible_child_name("main")
            self.main_stack.set_visible_child_name("menu")
            if hasattr(self, 'sidebar_search_entry'):
                self.sidebar_search_entry.set_text("")
            child = self.search_results_list.get_first_child()
            while child:
                self.search_results_list.remove(child)
                child = self.search_results_list.get_first_child()
        
        self.content_stack.set_visible_child_name(target)
        
        if target == "installed":
            self.installed_apps_widget.load_installed_apps()
        elif target == "updates":
            self.trigger_updates_check()
        elif target == "pulsar_store":
            self.pulsar_store_widget.load_catalog_async()
        elif target == "gnome_extensions" and hasattr(self, 'gnome_extensions_widget'):
            self.gnome_extensions_widget.refresh_active_tab()

    def setup_store_menus(self):
        # --- Main Menu View (App Store Homepage) ---
        scrolled_main = Gtk.ScrolledWindow()
        scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.main_stack.add_named(scrolled_main, "menu")
        
        # Expand size to 1000 for standard grid display
        clamp = Adw.Clamp(); clamp.set_maximum_size(1000)
        scrolled_main.set_child(clamp)
        
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.main_box.set_margin_top(24); self.main_box.set_margin_bottom(24)
        self.main_box.set_margin_start(24); self.main_box.set_margin_end(24)
        clamp.set_child(self.main_box)

        # --- Google AI Mode Search Card ---
        # English: Ask Google AI Mode which app you need and open the answer
        # in the default browser of the system.
        # Español: Preguntar a Google AI Mode qué app necesitas y abrir la
        # respuesta en el navegador predeterminado del sistema.
        ai_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        ai_card.add_css_class("card")
        ai_card.set_margin_bottom(8)

        ai_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        ai_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        ai_icon.set_pixel_size(28)
        ai_header.append(ai_icon)

        ai_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        ai_text_box.set_hexpand(True)

        ai_title = Gtk.Label(label=_("¿Qué aplicación necesitas?"), xalign=0)
        ai_title.add_css_class("title-label")
        ai_text_box.append(ai_title)

        ai_desc = Gtk.Label(label=_("Pregunta a Google AI Mode qué app necesitas para lo que buscas y luego instálala con un clic."), xalign=0)
        ai_desc.add_css_class("subtitle-label")
        ai_desc.set_wrap(True)
        ai_text_box.append(ai_desc)

        ai_header.append(ai_text_box)
        ai_card.append(ai_header)

        ai_entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.ai_search_entry = Gtk.Entry()
        self.ai_search_entry.set_placeholder_text(_("Por ejemplo: app para editar fotos o crear PDF..."))
        self.ai_search_entry.set_hexpand(True)
        self.ai_search_entry.connect("activate", lambda e: self.on_ai_mode_search_clicked(e))
        ai_entry_row.append(self.ai_search_entry)

        ai_search_btn = Gtk.Button(label=_("Buscar con IA"))
        ai_search_btn.add_css_class("suggested-action")
        ai_search_btn.connect("clicked", self.on_ai_mode_search_clicked)
        ai_entry_row.append(ai_search_btn)

        ai_card.append(ai_entry_row)
        self.main_box.append(ai_card)

        # English: Offline warning banner (hidden until we detect no internet)
        # Español: Aviso de modo sin conexión (oculto hasta detectar que no hay internet)
        self.offline_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.offline_banner.add_css_class("card")

        offline_icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        offline_icon.set_pixel_size(28)
        self.offline_banner.append(offline_icon)

        offline_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        offline_text_box.set_hexpand(True)

        offline_title = Gtk.Label(label=_("No se han podido cargar las aplicaciones sugeridas"), xalign=0)
        offline_title.add_css_class("title-label")
        offline_text_box.append(offline_title)

        offline_desc = Gtk.Label(label=_("Sin conexión a internet solo puedes instalar paquetes locales."), xalign=0)
        offline_desc.add_css_class("subtitle-label")
        offline_desc.set_wrap(True)
        offline_text_box.append(offline_desc)

        self.offline_banner.append(offline_text_box)
        self.offline_banner.set_visible(False)
        self.main_box.append(self.offline_banner)
        
        # 0. Secciones de recomendaciones curadas (recommendations.json)
        # English: One section per entry in the curated recommendations file
        # published in the repository, filtered by what this host can install.
        # Español: Una sección por cada entrada del archivo de recomendaciones
        # curadas publicado en el repositorio, filtradas por lo que este equipo
        # puede instalar realmente.
        self.recommended_sections_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.recommended_sections_box.set_margin_top(4)
        self.main_box.append(self.recommended_sections_box)

        # 4. Local File Installation Banner (Moved to bottom)
        local_install_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        local_install_card.add_css_class("card")
        local_install_card.set_margin_bottom(8)
        
        banner_icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        banner_icon.set_pixel_size(32)
        local_install_card.append(banner_icon)
        
        banner_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        banner_text_box.set_hexpand(True)
        
        banner_title = Gtk.Label(label=_("¿Tienes un archivo de paquete local?"), xalign=0)
        banner_title.add_css_class("title-label")
        banner_text_box.append(banner_title)
        
        banner_desc = Gtk.Label(label=_("Instala archivos .deb, .rpm, .pkg.tar.zst o PWAs directamente en tu sistema."), xalign=0)
        banner_desc.add_css_class("subtitle-label")
        banner_text_box.append(banner_desc)
        
        local_install_card.append(banner_text_box)
        
        buttons_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        choose_file_btn = Gtk.Button(label=_("Seleccionar archivo..."))
        choose_file_btn.connect("clicked", self.on_file_chooser_clicked)
        buttons_vbox.append(choose_file_btn)
        
        create_pwa_btn = Gtk.Button(label=_("Crear PWA..."))
        create_pwa_btn.add_css_class("secondary-button")
        create_pwa_btn.connect("clicked", self.on_pwa_clicked)
        buttons_vbox.append(create_pwa_btn)
        
        local_install_card.append(buttons_vbox)
        self.main_box.append(local_install_card)
        
        # Selected File Indicator (hidden/shown dynamically)
        self.selected_file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.selected_file_box.add_css_class("card")
        self.selected_file_box.set_visible(False)
        
        self.selected_file_label = Gtk.Label(label=_("Aún no has seleccionado ningún archivo"))
        self.selected_file_label.add_css_class("subtitle-label")
        self.selected_file_box.append(self.selected_file_label)
        
        file_actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.install_button = Gtk.Button(label=_("Instalar"))
        self.install_button.add_css_class("action-button")
        self.install_button.connect("clicked", self.on_install_clicked)
        file_actions_box.append(self.install_button)
        
        self.fix_deps_button = Gtk.Button(label=_("Corregir dependencias"))
        self.fix_deps_button.add_css_class("secondary-button")
        self.fix_deps_button.connect("clicked", self.on_fix_deps_clicked)
        file_actions_box.append(self.fix_deps_button)
        
        self.selected_file_box.append(file_actions_box)
        self.main_box.append(self.selected_file_box)
        
        # Progress / Status section (for when installing local file)
        self.progress_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.progress_section.add_css_class("card")
        self.progress_section.set_visible(False)
        self.progress_bar = Gtk.ProgressBar(); self.progress_bar.add_css_class("progress-bar")
        self.progress_section.append(self.progress_bar)
        self.status_label = Gtk.Label(label=_("Listo para empezar"))
        self.status_label.add_css_class("status-label")
        self.progress_section.append(self.status_label)
        self.main_box.append(self.progress_section)
        
        # --- Search Results View ---
        results_scrolled = Gtk.ScrolledWindow()
        results_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        results_scrolled.set_propagate_natural_width(False)
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        results_box.set_margin_top(24); results_box.set_margin_bottom(24)
        results_box.set_margin_start(24); results_box.set_margin_end(24)
        results_scrolled.set_child(results_box)
        
        self.search_results_list = Gtk.ListBox()
        self.search_results_list.add_css_class("navigation-sidebar")
        self.search_results_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_results_list.connect("row-activated", self.on_search_result_activated)
        results_box.append(self.search_results_list)
        
        self.search_spinner = Gtk.Spinner(); self.search_spinner.set_size_request(32, 32)
        self.search_spinner.set_halign(Gtk.Align.CENTER)
        results_box.append(self.search_spinner)
        
        self.main_stack.add_named(results_scrolled, "search_results")
        self.search_timer = None
        
        # Fetch Recommendations in the background
        self.load_store_recommendations()

    def on_ai_mode_search_clicked(self, widget=None):
        # English: Open the user's query in Google AI Mode (udm=50) using the
        # default browser of the system, in a new tab.
        # Español: Abrir la consulta del usuario en Google AI Mode (udm=50) con
        # el navegador predeterminado del sistema, en una pestaña nueva.
        entry = getattr(self, 'ai_search_entry', None)
        query = entry.get_text().strip() if entry is not None else ""

        if not query:
            if entry is not None:
                entry.grab_focus()
            self.status_label.set_text(_("Escribe qué aplicación necesitas antes de buscar con IA"))
            return

        prompt = _(
            "Encuentra una aplicación de escritorio para Linux que cubra esta necesidad. "
            "Dime el nombre exacto del paquete, si está disponible en Flatpak, AUR, Snap o en los "
            "repositorios oficiales, y el comando exacto para instalarla."
        )

        if open_google_ai_mode(query, prompt_prefix=prompt):
            entry.set_text("")
            self.status_label.set_text(_("Consulta abierta en Google AI Mode"))
            # English: GNOME does not always raise the new browser window, so
            # tell the user where to look for it.
            # Español: GNOME no siempre trae la ventana nueva del navegador al
            # frente, así que le avisamos de dónde tiene que mirarla.
            self._show_toast(_("Se ha abierto una ventana nueva en tu navegador"))
        else:
            self.status_label.set_text(_("No se pudo abrir Google AI Mode en el navegador"))
            self._show_toast(_("No se pudo abrir Google AI Mode en el navegador"))

    def _show_toast(self, message, timeout=2):
        """Muestra un aviso breve en la ventana (2 segundos por defecto).

        English: Shows a short message inside the app. It is used to tell the
        user that the browser was opened, because GNOME does not always focus
        the new window.
        Español: Muestra un aviso breve dentro de la aplicación. Se usa para
        avisar de que el navegador se ha abierto, porque GNOME no siempre
        enfoca la ventana nueva.
        """
        try:
            toast = Adw.Toast.new(message)
            toast.set_timeout(timeout)
            self.toast_overlay.add_toast(toast)
        except Exception as e:
            print(f"Error mostrando el aviso: {e}")

    def on_search_entry_activated(self, entry):
        text = entry.get_text().strip()
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None
        if len(text) >= 3:
            self.perform_package_search(text)

    def on_sidebar_search_changed(self, entry):
        text = entry.get_text()
        if text:
            # Switch to "store" tab and search results view immediately!
            store_row = self.sidebar_list.get_row_at_index(0)
            if self.sidebar_list.get_selected_row() != store_row:
                self.sidebar_list.select_row(store_row)
                
            self.content_stack.set_visible_child_name("store")
            self.header_stack.set_visible_child_name("search")
            self.main_stack.set_visible_child_name("search_results")
            
            stripped_text = text.strip()
            if len(stripped_text) >= 1:
                if self.search_timer:
                    GLib.source_remove(self.search_timer)
                self.search_timer = GLib.timeout_add(150, self.perform_package_search, stripped_text)
        else:
            # If search text is empty, switch back to home menu of the store
            self.header_stack.set_visible_child_name("main")
            self.main_stack.set_visible_child_name("menu")
            # Clear search results list
            child = self.search_results_list.get_first_child()
            while child:
                self.search_results_list.remove(child)
                child = self.search_results_list.get_first_child()

    def on_sidebar_search_activated(self, entry):
        text = entry.get_text().strip()
        if text:
            store_row = self.sidebar_list.get_row_at_index(0)
            if self.sidebar_list.get_selected_row() != store_row:
                self.sidebar_list.select_row(store_row)
            self.content_stack.set_visible_child_name("store")
            self.header_stack.set_visible_child_name("search")
            self.main_stack.set_visible_child_name("search_results")
            if len(text) >= 1:
                self.perform_package_search(text)

    def navigate_to_page(self, page_name):
        row = None
        for i in range(10):
            r = self.sidebar_list.get_row_at_index(i)
            if r and getattr(r, 'target_page', None) == page_name:
                row = r
                break
        if row:
            self.sidebar_list.select_row(row)
            self.content_stack.set_visible_child_name(page_name)

    def load_store_recommendations(self):
        """English: Render the curated sections from recommendations.json.

        The file is published in the repository, so new sections can be added
        without touching code. Each app declares its source (flatpak, apt, aur,
        pulsar, gnome-extension, ...) and it is only shown when this host can
        actually install it.
        Español: Dibuja en el inicio las secciones definidas en
        recommendations.json. Cada app declara su fuente y solo se muestra si
        este equipo puede instalarla realmente.
        """
        sections = []
        if self.recommendations_service is not None:
            try:
                sections = self.recommendations_service.load_sections()
            except Exception as e:
                print(f"Error loading recommendations.json: {e}")

        GLib.idle_add(self._render_recommended_sections, sections)

    def _render_recommended_sections(self, sections):
        """English: Draw one section per entry of the curated JSON file.
        Español: Dibuja una sección por cada entrada del JSON curado."""
        if not hasattr(self, 'recommended_sections_box'):
            return

        child = self.recommended_sections_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.recommended_sections_box.remove(child)
            child = nxt

        if not sections:
            return

        for section in sections:
            section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = Gtk.Label(label=section.get('title') or _('Recomendados'), xalign=0)
            title.add_css_class("store-section-title")
            title.set_hexpand(True)
            header.append(title)
            section_box.append(header)

            desc = section.get('desc') or ''
            if desc:
                desc_lbl = Gtk.Label(label=desc, xalign=0)
                desc_lbl.add_css_class("subtitle-label")
                desc_lbl.set_wrap(True)
                section_box.append(desc_lbl)

            cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            cards.set_margin_top(4)
            cards.set_margin_bottom(8)
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scrolled.set_child(cards)
            section_box.append(scrolled)

            self._fill_horizontal_cards(cards, section.get('apps', []))
            self.recommended_sections_box.append(section_box)

    def show_offline_banner(self):
        # English: Show the offline warning on the home screen (still used by
        # the remote search fallback)
        # Español: Mostrar el aviso de modo sin conexión en la pantalla de inicio
        if hasattr(self, 'offline_banner'):
            self.offline_banner.set_visible(True)

    def _fill_horizontal_cards(self, container, items):
        child = container.get_first_child()
        while child:
            container.remove(child)
            child = container.get_first_child()

        for item in items:
            card = self.create_highlight_card(item)
            container.append(card)

    def create_highlight_card(self, app_data):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        card.set_size_request(240, -1)
        card.set_hexpand(False)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Rounded App Icon (supports local files, SVG, GIF, WebP, PNG, cached icons, and symbolic names)
        from src.utils.system import create_app_icon_widget
        icon_path = app_data.get('icon', '')
        icon = create_app_icon_widget(icon_path, size=44, fallback="system-software-install-symbolic", package_id=app_data.get('name', 'app'))
        icon.add_css_class("app-card-icon")
        top_row.append(icon)


        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        title_box.set_valign(Gtk.Align.CENTER)

        name_lbl = Gtk.Label(label=app_data.get('display_name', app_data.get('name', '')), xalign=0)
        name_lbl.add_css_class("app-card-title")
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        title_box.append(name_lbl)

        source = app_data.get('source', '')
        if source == 'pulsar':
            sub_text = app_data.get('type', 'Pulsar').replace('_', ' ').capitalize()
        elif source == 'gnome-extension':
            sub_text = _("Extensión")
        else:
            sub_text = app_data.get('desc', '')

        sub_lbl = Gtk.Label(label=sub_text, xalign=0)
        sub_lbl.add_css_class("app-card-subtitle")
        sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        title_box.append(sub_lbl)

        top_row.append(title_box)
        card.append(top_row)

        desc_lbl = Gtk.Label(label=app_data.get('desc', ''), xalign=0)
        desc_lbl.add_css_class("subtitle-label")
        desc_lbl.set_wrap(True)
        desc_lbl.set_lines(2)
        desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        desc_lbl.set_vexpand(True)
        card.append(desc_lbl)

        btn = Gtk.Button(label=_("Ver") if source != 'gnome-extension' else _("Explorar"))
        btn.add_css_class("app-card-button")
        btn.set_halign(Gtk.Align.END)
        btn.connect("clicked", lambda b, data=app_data: self.on_recommendation_clicked(data))
        card.append(btn)

        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", lambda g, n, x, y, data=app_data: self.on_recommendation_clicked(data))
        card.add_controller(click_gesture)

        return card

    def create_app_grid_item(self, app_data):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.add_css_class("store-app-card")
        box.set_hexpand(True)
        box.set_valign(Gtk.Align.CENTER)
        
        # Rounded App Icon (supports local files, cached icons, and symbolic names)
        from src.utils.system import create_app_icon_widget
        icon_path = app_data.get('icon', '')
        icon = create_app_icon_widget(icon_path, size=48, fallback="system-software-install-symbolic", package_id=app_data.get('name', 'app'))
        icon.add_css_class("app-card-icon")
        box.append(icon)

        
        # Text labels
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)
        
        # Use ScrollingTextContainer for marquee text effect
        name_scroll = ScrollingTextContainer(app_data.get('display_name', ''), "app-card-title")
        vbox.append(name_scroll)
        
        desc_scroll = ScrollingTextContainer(app_data.get('desc', ''), "app-card-subtitle")
        vbox.append(desc_scroll)
        
        box.append(vbox)
        
        # Ver Button
        ver_btn = Gtk.Button(label=_("Ver"))
        ver_btn.add_css_class("app-card-button")
        ver_btn.set_valign(Gtk.Align.CENTER)
        ver_btn.connect("clicked", lambda b, data=app_data: self.on_recommendation_clicked(data))
        box.append(ver_btn)
        
        # Connect click gesture to the box to open install page from anywhere on the card
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", lambda g, n, x, y, data=app_data: self.on_recommendation_clicked(data))
        box.add_controller(click_gesture)
        
        # Add hover controller to trigger text marquee scrolling
        hover_controller = Gtk.EventControllerMotion()
        
        def on_hover_enter(controller, x, y):
            name_scroll.start_scrolling()
            desc_scroll.start_scrolling()
            
        def on_hover_leave(controller):
            name_scroll.stop_scrolling()
            desc_scroll.stop_scrolling()
            
        hover_controller.connect("enter", on_hover_enter)
        hover_controller.connect("leave", on_hover_leave)
        box.add_controller(hover_controller)
        
        return box

    def create_top_free_card(self, rank, app_data):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("top-free-card")
        card.set_size_request(140, 200)
        card.set_hexpand(True)
        
        # Rank Number
        rank_label = Gtk.Label(label=str(rank), xalign=0)
        rank_label.add_css_class("top-free-rank")
        card.append(rank_label)
        
        # Centered rounded app icon
        icon_path = app_data.get('icon', '')
        if icon_path and os.path.exists(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
        icon.set_pixel_size(64)
        icon.set_halign(Gtk.Align.CENTER)
        icon.add_css_class("app-card-icon")
        card.append(icon)
        
        # Centered app name
        name_label = Gtk.Label(label=app_data.get('display_name', ''))
        name_label.add_css_class("top-free-title")
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_halign(Gtk.Align.CENTER)
        card.append(name_label)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        card.append(spacer)
        
        # Ver Button (centered)
        ver_btn = Gtk.Button(label=_("Ver"))
        ver_btn.add_css_class("app-card-button")
        ver_btn.set_halign(Gtk.Align.CENTER)
        ver_btn.connect("clicked", lambda b, data=app_data: self.on_recommendation_clicked(data))
        card.append(ver_btn)
        
        # Make the entire top-free card clickable
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", lambda g, n, x, y, data=app_data: self.on_recommendation_clicked(data))
        card.add_controller(click_gesture)
        
        return card

    def on_recommendation_clicked(self, app_data):
        pkg_name = app_data['name']
        source = app_data.get('source', '')
        if source == 'gnome-extension' or source == 'gnome-ext':
            pkg_name = f"gnome-ext:{pkg_name}"
        elif source == 'flatpak':
            pkg_name = f"flatpak:{pkg_name}"
        elif source == 'pulsar':
            pkg_name = f"pulsar:{pkg_name}"
        self.file_path = pkg_name
        self.show_package_details(identifier=pkg_name, is_local=False)

    def setup_updates_widget(self):
        updates_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)
        header_bar.set_show_start_title_buttons(True)
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Actualizaciones")))
        header_bar.add_css_class("header-bar")
        updates_box.append(header_bar)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        updates_box.append(scrolled)
        
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24); content.set_margin_bottom(24)
        content.set_margin_start(24); content.set_margin_end(24)
        scrolled.set_child(content)
        
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_card.add_css_class("card")
        status_card.set_halign(Gtk.Align.FILL)
        
        self.updates_status_icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
        self.updates_status_icon.set_pixel_size(48)
        status_card.append(self.updates_status_icon)
        
        self.updates_status_label = Gtk.Label(label=_("Comprobando actualizaciones..."))
        self.updates_status_label.add_css_class("title-label")
        status_card.append(self.updates_status_label)
        
        self.updates_spinner = Gtk.Spinner()
        self.updates_spinner.set_size_request(32, 32)
        status_card.append(self.updates_spinner)
        
        content.append(status_card)
        
        # ── Actualizaciones automáticas (toggle) ────────────────────────────
        auto_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        auto_card.add_css_class("card")
        auto_card.set_halign(Gtk.Align.FILL)
        
        auto_texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        auto_title = Gtk.Label(label=_("Actualizaciones automáticas"), xalign=0)
        auto_title.add_css_class("title-label")
        auto_subtitle = Gtk.Label(
            label=_("Instala automáticamente en segundo plano las actualizaciones del sistema y de las aplicaciones."),
            xalign=0, wrap=True,
        )
        auto_subtitle.add_css_class("dim-label")
        auto_texts.append(auto_title)
        auto_texts.append(auto_subtitle)
        auto_card.append(auto_texts)
        
        self.auto_update_switch = Gtk.Switch()
        self.auto_update_switch.set_valign(Gtk.Align.CENTER)
        self.auto_update_switch.set_active(self._load_auto_update())
        self.auto_update_switch.connect("state-set", self.on_auto_update_toggled)
        auto_card.append(self.auto_update_switch)
        
        content.append(auto_card)
        
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions_box.set_halign(Gtk.Align.CENTER)
        
        self.check_updates_btn = Gtk.Button(label=_("Comprobar ahora"))
        self.check_updates_btn.connect("clicked", lambda b: self.trigger_updates_check())
        actions_box.append(self.check_updates_btn)
        
        self.upgrade_all_btn = Gtk.Button(label=_("Actualizar todo"))
        self.upgrade_all_btn.add_css_class("suggested-action")
        self.upgrade_all_btn.set_sensitive(False)
        self.upgrade_all_btn.connect("clicked", lambda b: self.trigger_system_upgrade())
        actions_box.append(self.upgrade_all_btn)
        
        content.append(actions_box)
        
        self.updates_listbox = Gtk.ListBox()
        self.updates_listbox.add_css_class("navigation-sidebar")
        self.updates_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        
        updates_list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        updates_list_container.set_margin_top(12)
        updates_list_container.append(self.updates_listbox)
        content.append(updates_list_container)
        
        return updates_box

    def _load_auto_update(self) -> bool:
        """Lee la preferencia 'auto_update' de la configuración (activa por defecto)."""
        try:
            for path in (
                os.path.expanduser("~/.config/appinstall/config.json"),
                "/etc/appinstall/config.json",
            ):
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "auto_update" in data:
                            return bool(data["auto_update"])
        except Exception as e:
            print(f"Error reading auto_update configuration: {e}")
        return True

    def on_auto_update_toggled(self, switch, state):
        """Persiste el estado del interruptor de actualizaciones automáticas."""
        try:
            path = os.path.expanduser("~/.config/appinstall/config.json")
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["auto_update"] = bool(state)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving auto_update configuration: {e}")
            switch.set_active(not state)  # revertir el interruptor
            return True

        # El daemon relee la configuración en cada ciclo, así que con activar
        # el interruptor basta para que empiecen a llegar las actualizaciones.
        if state:
            self._ensure_auto_update_loop()
        return True

    def _ensure_auto_update_loop(self):
        """English: Start the background auto-update loop if it is not running.

        The daemon re-reads the configuration on every cycle, so turning the
        switch on is enough to start receiving automatic updates.
        Español: Arranca en segundo plano el ciclo de actualizaciones
        automáticas si no está ya corriendo.
        """
        if getattr(self, "_auto_update_thread", None) and self._auto_update_thread.is_alive():
            return

        def _run():
            try:
                from src.application.daemon_service import DaemonService
                DaemonService().run_loop(first_delay_seconds=10)
            except Exception as e:
                print(f"Error in auto-update worker: {e}")

        self._auto_update_thread = threading.Thread(target=_run, daemon=True)
        self._auto_update_thread.start()

    def trigger_updates_check(self):
        self.updates_spinner.start()
        self.updates_spinner.set_visible(True)
        self.updates_status_label.set_text(_("Comprobando actualizaciones..."))
        self.upgrade_all_btn.set_sensitive(False)

        # Barra de progreso inferior mientras se busca
        if self._updates_check_op_id is None:
            self._updates_check_op_id = self._show_progress(_("Buscando actualizaciones..."))
        
        child = self.updates_listbox.get_first_child()
        while child:
            self.updates_listbox.remove(child)
            child = self.updates_listbox.get_first_child()

        def _check():
            try:
                import shutil
                import urllib.request
                # Actualizar automáticamente los repositorios del sistema
                try:
                    update_cmd = self.pkg_manager.update_cache()
                    if update_cmd:
                        subprocess.run(update_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
                except Exception as e:
                    print(f"Error updating package cache: {e}")

                latest_app_version = self.update_service.get_latest_version()
                appinstall_upgradable = latest_app_version and latest_app_version != CURRENT_VERSION
                
                upgradable_pkgs = []
                try:
                    if shutil.which('pacman'):
                        try:
                            output = subprocess.check_output(['pacman', '-Qu'], stderr=subprocess.DEVNULL, timeout=10).decode('utf-8')
                            for line in output.split('\n'):
                                if line.strip():
                                    parts = line.split()
                                    if len(parts) >= 2:
                                        upgradable_pkgs.append(parts[0])
                        except subprocess.CalledProcessError as e:
                            if e.returncode != 1:
                                print(f"pacman check-updates error: {e}")
                    elif shutil.which('apt'):
                        try:
                            output = subprocess.check_output(['apt', 'list', '--upgradable'], stderr=subprocess.DEVNULL, timeout=10).decode('utf-8')
                            for line in output.split('\n'):
                                if line.strip() and 'upgradable' in line and not line.startswith('Listing...'):
                                    pkg = line.split('/')[0]
                                    upgradable_pkgs.append(pkg)
                        except Exception as e:
                            print(f"apt check-updates error: {e}")
                    elif shutil.which('dnf'):
                        try:
                            res = subprocess.run(['dnf', 'check-update', '-q'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
                            if res.returncode in [0, 100]:
                                output = res.stdout.decode('utf-8')
                                for line in output.split('\n'):
                                    if line.strip():
                                        parts = line.split()
                                        if len(parts) >= 2 and parts[0] != 'Obtaining':
                                            upgradable_pkgs.append(parts[0])
                        except Exception as e:
                            print(f"dnf check-updates error: {e}")
                except Exception as e:
                    print(f"Error checking system updates: {e}")

                # Check Flatpak updates
                upgradable_flatpaks = []
                if shutil.which('flatpak'):
                    try:
                        res = subprocess.run(['flatpak', 'remote-ls', '--updates'], capture_output=True, text=True, timeout=10)
                        if res.returncode == 0:
                            for l in res.stdout.splitlines():
                                if l.strip():
                                    parts = l.split()
                                    if parts:
                                        upgradable_flatpaks.append(parts[0])
                    except Exception:
                        pass

                # Check Pulsar Store updates
                upgradable_pulsar = []
                try:
                    from src.infrastructure.adapters.pulsar_store_adapter import _load_installed_db
                    installed_db = _load_installed_db()
                    if installed_db:
                        catalog = self.info_service.pulsar_adapter._get_catalog()
                        for pkg_id, inst_meta in installed_db.items():
                            cat_pkg = self.info_service.pulsar_adapter._find_pkg(catalog, pkg_id)
                            if cat_pkg and cat_pkg.get('version'):
                                cur_ver = str(inst_meta.get('version', ''))
                                new_ver = str(cat_pkg.get('version', ''))
                                if cur_ver and new_ver and cur_ver != new_ver:
                                    upgradable_pulsar.append({
                                        'id': pkg_id,
                                        'name': cat_pkg.get('name', pkg_id),
                                        'new_version': new_ver,
                                        'current_version': cur_ver,
                                    })
                except Exception as e:
                    print(f"Error checking Pulsar Store updates: {e}")

                # Check GNOME Extensions updates
                upgradable_extensions = []
                try:
                    user_ext_dir = os.path.expanduser("~/.local/share/gnome-shell/extensions")
                    if os.path.isdir(user_ext_dir):
                        for entry in os.listdir(user_ext_dir):
                            meta_p = os.path.join(user_ext_dir, entry, "metadata.json")
                            if os.path.isfile(meta_p):
                                try:
                                    with open(meta_p, 'r', encoding='utf-8', errors='ignore') as mf:
                                        local_meta = json.load(mf)
                                    uuid = local_meta.get('uuid', entry)
                                    name = local_meta.get('name', uuid)
                                    local_ver = str(local_meta.get('version', ''))
                                    ego_url = f"https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(uuid)}"
                                    req = urllib.request.Request(ego_url, headers={"User-Agent": "AppInstall/1.0"})
                                    with urllib.request.urlopen(req, timeout=4) as resp:
                                        data = json.loads(resp.read().decode('utf-8'))
                                        for ext_obj in data.get('extensions', []):
                                            if ext_obj.get('uuid') == uuid:
                                                # Check pk details for shell version
                                                pk = ext_obj.get('pk')
                                                if pk:
                                                    info_req = urllib.request.Request(f"https://extensions.gnome.org/extension-info/?pk={pk}", headers={"User-Agent": "AppInstall/1.0"})
                                                    with urllib.request.urlopen(info_req, timeout=4) as info_resp:
                                                        ext_info = json.loads(info_resp.read().decode('utf-8'))
                                                        shell_map = ext_info.get('shell_version_map', {})
                                                        if shell_map:
                                                            latest_v = list(shell_map.values())[-1]
                                                            latest_ver_num = str(latest_v.get('version', '')) if isinstance(latest_v, dict) else ''
                                                            if latest_ver_num and local_ver and latest_ver_num != local_ver:
                                                                upgradable_extensions.append({
                                                                    'uuid': uuid,
                                                                    'name': name,
                                                                    'new_version': latest_ver_num,
                                                                    'current_version': local_ver
                                                                })
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"Error checking GNOME extensions updates: {e}")
                    
                GLib.idle_add(self.show_updates_results, appinstall_upgradable, latest_app_version, upgradable_pkgs, upgradable_flatpaks, upgradable_pulsar, upgradable_extensions)
            except Exception as e:
                print(f"Error in updates check thread: {e}")
                GLib.idle_add(self.show_updates_error)
                
        threading.Thread(target=_check, daemon=True).start()

    def show_updates_results(self, appinstall_upgradable, latest_app_version, upgradable_pkgs, upgradable_flatpaks=None, upgradable_pulsar=None, upgradable_extensions=None):
        self.updates_spinner.stop()
        self.updates_spinner.set_visible(False)
        self._finish_updates_check_progress()
        
        upgradable_flatpaks = upgradable_flatpaks or []
        upgradable_pulsar = upgradable_pulsar or []
        upgradable_extensions = upgradable_extensions or []

        total_updates = len(upgradable_pkgs) + len(upgradable_flatpaks) + len(upgradable_pulsar) + len(upgradable_extensions) + (1 if appinstall_upgradable else 0)
        
        if total_updates == 0:
            self.updates_status_icon.set_from_icon_name("emblem-ok-symbolic")
            self.updates_status_label.set_text(_("El sistema está actualizado"))
            self.upgrade_all_btn.set_sensitive(False)
        else:
            self.updates_status_icon.set_from_icon_name("software-update-available-symbolic")
            self.updates_status_label.set_text(_("Tienes {} actualizaciones disponibles").format(total_updates))
            self.upgrade_all_btn.set_sensitive(True)
            
            if appinstall_upgradable:
                self.add_update_row("AppInstall", _("Nueva versión disponible: {} (actual: {})").format(latest_app_version, CURRENT_VERSION), is_app=True)
                
            for p in upgradable_pulsar:
                self.add_update_row(p['name'], _("Pulsar Store: versión {} disponible (actual: {})").format(p['new_version'], p['current_version']), icon_name="emblem-favorite-symbolic")

            for ext in upgradable_extensions:
                self.add_update_row(ext['name'], _("Extensión GNOME: versión {} disponible (actual: {})").format(ext['new_version'], ext['current_version']), icon_name="application-x-addon-symbolic")

            for f in upgradable_flatpaks:
                self.add_update_row(f, _("Actualización disponible en Flathub"), icon_name="package-x-generic-symbolic")

            # Lista completa: se muestran todas las actualizaciones disponibles
            for pkg in upgradable_pkgs:
                self.add_update_row(pkg, _("Actualización disponible de los repositorios del sistema"))

    def _finish_updates_check_progress(self):
        """Quita la barra de progreso de la comprobación de actualizaciones."""
        if self._updates_check_op_id is not None:
            self._finish_operation(self._updates_check_op_id)
            self._updates_check_op_id = None

    def add_update_row(self, name, description, is_app=False, icon_name=None):
        row = Gtk.ListBoxRow()
        row.add_css_class("list-row")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8); box.set_margin_bottom(8)
        box.set_margin_start(8); box.set_margin_end(8)
        
        icon_to_use = icon_name if icon_name else ("es.inled.AppInstall" if is_app else "package-x-generic-symbolic")
        icon = Gtk.Image.new_from_icon_name(icon_to_use)
        box.append(icon)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        
        name_label = Gtk.Label(label=name, xalign=0)
        name_label.add_css_class("title-label")
        vbox.append(name_label)
        
        desc_label = Gtk.Label(label=description, xalign=0)
        desc_label.add_css_class("subtitle-label")
        vbox.append(desc_label)
        
        box.append(vbox)
        row.set_child(box)
        self.updates_listbox.append(row)

    def show_updates_error(self):
        self.updates_spinner.stop()
        self.updates_spinner.set_visible(False)
        self._finish_updates_check_progress()
        self.updates_status_icon.set_from_icon_name("dialog-error-symbolic")
        self.updates_status_label.set_text(_("Error al comprobar actualizaciones"))
        
    def trigger_system_upgrade(self):
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))
        self.main_stack.set_visible_child_name("menu")
        self.on_upgrade_system_clicked(None)

    def _on_close_request(self, *args):
        # English: Ensure the Python process exits completely upon window close
        # Español: Asegurar que el proceso de Python se cierre por completo al cerrar la ventana
        import os
        os._exit(0)

    def on_fake_search_clicked(self, btn):
        # Cambiar a modo búsqueda
        self.header_stack.set_visible_child_name("search")
        self.main_stack.set_visible_child_name("search_results")
        
        # Enfocar la entrada real de la barra lateral
        if hasattr(self, 'sidebar_search_entry'):
            GLib.timeout_add(100, self.sidebar_search_entry.grab_focus)

    def on_search_back_clicked(self, btn):
        if hasattr(self, 'sidebar_search_entry'):
            self.sidebar_search_entry.set_text("")

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
        if self.file_path:
            is_scheme = any(self.file_path.startswith(prefix) for prefix in [
                "flatpak:", "snap:", "aur:", "brew:", "pulsar:", "pulsar-store:",
                "gnome-extension:", "gnome-extensions:", "gnome-ext:",
                "appstream:", "flatpak+https:"
            ])
            if is_scheme or os.path.exists(self.file_path):
                # Ensure store tab is active and visible
                store_row = self.sidebar_list.get_row_at_index(0)
                self.sidebar_list.select_row(store_row)
                self.content_stack.set_visible_child_name("store")
                
                if not is_scheme:
                    self.selected_file_label.set_text(_("Archivo seleccionado: {}").format(os.path.basename(self.file_path)))
                    self.selected_file_box.set_visible(True)
                    self.install_button.set_sensitive(True)
                    self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
                    GLib.idle_add(lambda: self.show_package_details(is_local=True))
                else:
                    _id = self.file_path
                    GLib.idle_add(lambda: self.show_package_details(identifier=_id, is_local=False))
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
                self.selected_file_box.set_visible(True)
                self.install_button.set_sensitive(True)
                self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
                self.show_package_details()
        dialog.destroy()

    def show_package_details(self, identifier=None, is_local=True):
        # Ensure store view stack is shown and active
        self.content_stack.set_visible_child_name("store")
        store_row = self.sidebar_list.get_row_at_index(0)
        self.sidebar_list.select_row(store_row)
        
        if not identifier:
            identifier = self.file_path if is_local else self.sidebar_search_entry.get_text().strip()
        if not identifier:
            return
            
        self.file_path = identifier
        self.status_label.set_text(_("Obteniendo información de la aplicación..."))
        op_id = self._show_progress(
            _("Analizando paquete..."),
            skip_callback=lambda: self.on_skip_analysis_clicked(op_id),
        )
        
        def _get_info():
            try:
                info = self.info_service.get_info(identifier, is_local=is_local)
                if info:
                    if is_local:
                        info['ext'] = os.path.splitext(identifier)[1].lstrip('.')
                    else:
                        info['ext'] = 'repo'
                    
                    # Comprobar si ya está instalado en el sistema
                    source = info.get('source', '')
                    # Para flatpak usar el app_id (reverse-DNS), no el nombre para mostrar
                    if source == 'flatpak':
                        flatpak_id = info.get('app_id') or (identifier.replace('flatpak:', '', 1) if identifier.startswith('flatpak:') else info.get('name', ''))
                    else:
                        flatpak_id = None
                    name = info.get('name', '')
                    is_installed = False
                    
                    try:
                        import shutil
                        if source == 'flatpak':
                            is_installed = subprocess.run(['flatpak', 'info', flatpak_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                        elif source == 'snap':
                            is_installed = subprocess.run(['snap', 'list', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                        elif source == 'aur':
                            is_installed = subprocess.run(['pacman', '-Qi', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                        elif source == 'brew':
                            if shutil.which('brew'):
                                is_installed = subprocess.run(['brew', 'list', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                        elif source == 'pulsar':
                            pkg_id = info.get('pulsar_id') or (identifier.replace('pulsar:', '', 1) if identifier.startswith('pulsar:') else name)
                            is_installed = self.info_service.pulsar_adapter.is_package_installed(pkg_id)
                        elif source in ['gnome-ext', 'gnome-extension']:
                            uuid = info.get('uuid') or (identifier.replace('gnome-ext:', '', 1).replace('gnome-extension:', '', 1) if identifier else name)
                            user_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{uuid}")
                            sys_dir = f"/usr/share/gnome-shell/extensions/{uuid}"
                            is_installed = (os.path.isdir(user_dir) and os.path.exists(os.path.join(user_dir, "metadata.json"))) or (os.path.isdir(sys_dir) and os.path.exists(os.path.join(sys_dir, "metadata.json")))
                        else:
                            # Paquete nativo de la distribución
                            if shutil.which('pacman'):
                                is_installed = subprocess.run(['pacman', '-Qi', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                            elif shutil.which('dpkg-query'):
                                res = subprocess.run(['dpkg-query', '-W', '-f=${Status}', name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                                is_installed = b'install ok installed' in res.stdout
                            elif shutil.which('rpm'):
                                is_installed = subprocess.run(['rpm', '-q', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                    except Exception as e:
                        print(f"Error checking if package is installed: {e}")
                        
                    info['is_installed'] = is_installed
                    info['identifier'] = identifier
                    
                GLib.idle_add(self._present_details_window, info, op_id)
            except Exception as e:
                print(f"Error getting package info: {e}")
                GLib.idle_add(self._hide_progress_and_error, op_id)
            
        threading.Thread(target=_get_info, daemon=True).start()

    def _hide_progress_and_error(self, op_id=None):
        self._close_progress_dialog(op_id)
        self.status_label.set_text(_("No he podido obtener detalles del paquete"))

    def _present_details_window(self, info, op_id=None):
        self._close_progress_dialog(op_id)
        self.status_label.set_text(_("Detalles de la aplicación cargados"))
        
        if hasattr(self, 'details_widget_instance') and self.details_widget_instance:
            try:
                self.main_stack.remove(self.details_widget_instance)
            except: pass
            
        prev_view = self.main_stack.get_visible_child_name()
        if prev_view not in ['menu', 'search_results']:
            prev_view = 'menu'
        self.details_prev_view = prev_view
        
        target_id = info.get('identifier') or self.file_path
        self.details_widget_instance = PackageDetailsWidget(
            self, 
            info, 
            on_install_callback=lambda tid=target_id: self.install_package_by_identifier(tid),
            on_uninstall_callback=lambda: self.uninstall_package_from_details(info.get('pulsar_id') or info.get('uuid') or info.get('name'), info.get('source')),
            back_callback=self.on_details_back_clicked
        )
        self.main_stack.add_named(self.details_widget_instance, "details")
        self.main_stack.set_visible_child_name("details")
        # Show the details toolbar (with close button) instead of hiding the header
        self.details_title_label.set_text(info.get('name', ''))
        self.header_stack.set_visible(True)
        self.header_stack.set_visible_child_name("details")

    def install_package_by_identifier(self, identifier):
        self.file_path = identifier
        self.on_install_clicked(None)

    def on_details_back_clicked(self, btn=None):
        self.header_stack.set_visible(True)
        if self.details_prev_view == "search_results":
            self.header_stack.set_visible_child_name("search")
        else:
            self.header_stack.set_visible_child_name("main")
        self.main_stack.set_visible_child_name(self.details_prev_view)
        if self.details_prev_view == "search_results":
            GLib.timeout_add(100, self.sidebar_search_entry.grab_focus)

    def uninstall_package_from_details(self, name, source):
        if source in ['gnome-ext', 'gnome-extension']:
            self.set_buttons_sensitive(False)
            token = prompt_engine.CancelToken()
            op_id = self._show_progress(_("Desinstalando extensión..."), cancel_token=token)
            user_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{name}")
            cmd = [
                "sh", "-c",
                f"(gdbus call --session --dest org.gnome.Shell.Extensions --object-path /org/gnome/Shell/Extensions --method org.gnome.Shell.Extensions.UninstallExtension '{name}' || true) && "
                f"(gnome-extensions uninstall '{name}' || true) && rm -rf '{user_dir}'"
            ]
            self.install_service.run_installation(
                cmd, f"uninstall:gnome-ext:{name}", self.update_progress_ui,
                self._operation_callback(op_id, self.on_uninstall_complete, token),
                on_log=self._operation_log_handler(op_id),
                cancel_token=token,
            )
            return

        if source == 'pulsar':
            self.set_buttons_sensitive(False)
            token = prompt_engine.CancelToken()
            op_id = self._show_progress(_("Desinstalando paquete..."), cancel_token=token)
            cmd = self.info_service.pulsar_adapter.uninstall(name)
            self.install_service.run_installation(
                cmd, f"uninstall:pulsar:{name}", self.update_progress_ui,
                self._operation_callback(op_id, self.on_uninstall_complete, token),
                on_log=self._operation_log_handler(op_id),
                cancel_token=token,
            )
            return

        is_flatpak = (source == 'flatpak')
        is_snap = (source == 'snap')
        is_aur = (source == 'aur')
        is_brew = (source == 'brew')
        
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(1))
        self.content_stack.set_visible_child_name("installed")
        
        self.installed_apps_widget.on_uninstall_clicked(
            None,
            name,
            is_flatpak=is_flatpak,
            is_snap=is_snap,
            is_aur=is_aur,
            is_brew=is_brew
        )

    def on_skip_analysis_clicked(self, op_id=None):
        # English: Skip package analysis and trigger installation directly
        # Español: Omitir el análisis del paquete e iniciar la instalación de inmediato
        self._close_progress_dialog(op_id)
        self.status_label.set_text(_("Análisis omitido, instalando..."))
        GLib.idle_add(lambda: self.on_install_clicked(None))

    def on_install_clicked(self, widget):
        if not self.file_path:
            package_name = self.sidebar_search_entry.get_text().strip()
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
        
        # AUR: mostrar el PKGBUILD y pedir confirmación antes de instalar
        if self.file_path.startswith('aur:'):
            pkg_name = self.file_path.replace('aur:', '', 1)
            self._show_aur_confirmation(pkg_name)
            return
        
        self._proceed_install()

    def _show_aur_confirmation(self, pkg_name):
        def _load():
            pkgbuild = ""
            try:
                pkgbuild = self.install_service.aur_adapter.get_pkgbuild(pkg_name)
            except Exception as e:
                print(f"Error fetching PKGBUILD for {pkg_name}: {e}")
            GLib.idle_add(self._present_aur_confirmation, pkg_name, pkgbuild)
        threading.Thread(target=_load, daemon=True).start()

    def _present_aur_confirmation(self, pkg_name, pkgbuild):
        dialog = Adw.AlertDialog(
            heading=_("Instalar desde AUR: {}").format(pkg_name),
            body=_("Este paquete se compilará e instalará desde el Arch User Repository. Revisa el PKGBUILD: cualquier archivo se ejecuta con tus permisos.")
        )
        if pkgbuild:
            extra_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_size_request(-1, 300)
            view = Gtk.TextView()
            view.set_editable(False)
            view.set_cursor_visible(False)
            view.add_css_class("pkgbuild-view")
            view.get_buffer().set_text(pkgbuild)
            scrolled.set_child(view)
            extra_box.append(scrolled)

            # English: Send the PKGBUILD to Google AI Mode to have it reviewed
            # Español: Enviar el PKGBUILD a Google AI Mode para que lo analice
            ai_btn = Gtk.Button(label=_("Analizar PKGBUILD con IA"))
            ai_btn.add_css_class("suggested-action")
            ai_btn.set_halign(Gtk.Align.CENTER)
            ai_btn.connect("clicked", lambda b, n=pkg_name, p=pkgbuild: self._analyze_pkgbuild_with_ai(n, p))
            extra_box.append(ai_btn)

            dialog.set_extra_child(extra_box)
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("install", _("Instalar"))
        dialog.set_default_response("cancel")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_aur_confirm_response)
        dialog.present(self)

    def _analyze_pkgbuild_with_ai(self, package_name, pkgbuild):
        # English: Open the PKGBUILD in Google AI Mode for a safety review
        # Español: Abrir el PKGBUILD en Google AI Mode para revisar su seguridad
        if analyze_pkgbuild_with_ai(pkgbuild, package_name):
            self.status_label.set_text(_("PKGBUILD enviado a Google AI Mode"))
        else:
            self.status_label.set_text(_("No se pudo abrir Google AI Mode en el navegador"))

    def _on_aur_confirm_response(self, dialog, response):
        if response == "install":
            self._proceed_install()

    def _proceed_install(self):
        cmd = self.install_service.get_install_command(self.file_path)
        if not cmd:
            self.status_label.set_text(_("Formato de paquete no soportado por App Install"))
            return

        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)

        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Instalando..."), cancel_token=token)

        self.install_service.run_installation(
            cmd, self.file_path, self.update_progress_ui,
            self._operation_callback(op_id, self.on_installation_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def install_flatpak_plugin(self, app_id, name=""):
        """Instala o reinstala un plugin (addon) de Flatpak.

        English: Installs or reinstalls a Flatpak plugin from the plugin list
        of the details view, showing the progress in the bottom bar.
        Español: Instala o reinstala un plugin (addon) de Flatpak desde la
        lista de plugins de la ficha, mostrando el progreso en la barra
        inferior.
        """
        if not app_id:
            return

        plugin_name = name or app_id
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Instalando plugin {}...").format(plugin_name))
        self.progress_bar.set_fraction(0.0)

        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Instalando plugin {}...").format(plugin_name), cancel_token=token)

        cmd = self.install_service.flatpak_adapter.install_addon(app_id)
        self.install_service.run_plugin_installation(
            cmd, plugin_name, self.update_progress_ui,
            self._operation_callback(op_id, self.on_plugin_install_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def on_plugin_install_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)

        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error al instalar el plugin!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He instalado el plugin"), body=message)

        self._present_result_dialog(dialog, is_error, log_text=stderr_output or message)
        self._sync_buttons_state()

    def on_fix_deps_clicked(self, widget):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Corregir errores"))
        self.progress_bar.set_fraction(0.0)

        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Corregir errores"), cancel_token=token)

        cmd = self.pkg_manager.fix_broken()
        self.install_service.run_fix_deps(
            cmd, self.update_progress_ui,
            self._operation_callback(op_id, self.on_fix_deps_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def on_upgrade_system_clicked(self, widget):
        # English: Trigger full system update and upgrade (including Flatpak)
        # Español: Desencadenar la actualización completa del sistema y aplicaciones
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Actualizando el sistema..."))
        self.progress_bar.set_fraction(0.0)
        
        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Actualizando el sistema..."), cancel_token=token)

        cmd = self.pkg_manager.upgrade_system()
        import shutil
        import shlex
        if shutil.which('flatpak'):
            if cmd and len(cmd) >= 2 and cmd[0] == 'pkexec':
                # English: Quote each argument so scripts ('sh -c ...') survive
                # Español: Comillas en cada argumento para que los scripts ('sh -c ...') se mantengan
                inner_cmd = shlex.join(cmd[1:])
                cmd = ['pkexec', 'sh', '-c', f"{inner_cmd} && (flatpak update -y || true)"]
            elif cmd:
                inner_cmd = shlex.join(cmd)
                cmd = ['sh', '-c', f"{inner_cmd} && (flatpak update -y || true)"]
        self.install_service.run_installation(
            cmd, "system_upgrade", self.update_progress_ui,
            self._operation_callback(op_id, self.on_upgrade_system_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def on_apps_clicked(self, widget):
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(1))

    def on_clean_clicked(self, widget):
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(3))

    def on_antivirus_clicked(self, widget):
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(4))

    def on_pwa_clicked(self, widget):
        pwa_window = PWAConfigWindow(self, self.proceed_with_pwa_installation)
        pwa_window.present()

    def proceed_with_appimage_installation(self, display_name, icon_path):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)

        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Instalando {}...").format(display_name), cancel_token=token)

        cmd = self.install_service.get_appimage_install_command(self.file_path, display_name, icon_path)
        self.install_service.run_installation(
            cmd, self.file_path, self.update_progress_ui,
            self._operation_callback(op_id, self.on_installation_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def proceed_with_pwa_installation(self, display_name, url, icon_path):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Creando PWA..."))
        self.progress_bar.set_fraction(0.0)

        token = prompt_engine.CancelToken()
        op_id = self._show_progress(_("Creando PWA {}...").format(display_name), cancel_token=token)

        cmd = self.install_service.get_pwa_install_command(display_name, url, icon_path)
        self.install_service.run_installation(
            cmd, None, self.update_progress_ui,
            self._operation_callback(op_id, self.on_installation_complete, token),
            on_log=self._operation_log_handler(op_id),
            cancel_token=token,
        )

    def on_operation_log(self, line):
        # English: Legacy entry point, sends the log line to the latest operation
        # Español: Entrada heredada, envía la línea de registro a la última operación
        op_id = getattr(self, '_last_operation_id', None)
        if op_id is not None:
            self.operation_bar.set_log(op_id, line)

    def _operation_log_handler(self, op_id):
        # English: Log handler bound to a concrete operation
        # Español: Manejador de registro asociado a una operación concreta
        def _handler(line):
            self.operation_bar.set_log(op_id, line)
        return _handler

    def _operation_callback(self, op_id, handler, cancel_token=None):
        # English: Wraps a completion callback so its operation row is removed
        # Español: Envuelve un callback de finalización para quitar su fila
        def _callback(message, is_error=False, stderr_output=""):
            cancelled = cancel_token is not None and cancel_token.was_terminated()
            self._finish_operation(op_id)
            if cancelled:
                # English: The user stopped it: no error dialog, just a note
                # Español: El usuario lo paró: sin diálogo de error, solo un aviso
                self.status_label.set_text(_("Operación cancelada"))
                self._sync_buttons_state()
                return
            handler(message, is_error, stderr_output)
        return _callback

    def _cancel_operation(self, op_id, cancel_token=None):
        # English: Stops a running operation from the bottom bar
        # Español: Detiene una operación en curso desde la barra inferior
        if op_id is None:
            return

        row = self.operation_bar.get_row(op_id)
        if row is not None:
            row.set_cancelling()
            row.set_title(_("Cancelando..."))

        if cancel_token is not None:
            try:
                cancel_token.cancel()
            except Exception as e:
                print(f"Error cancelando la operación: {e}")

        self.status_label.set_text(_("Cancelando la operación..."))

    def _finish_operation(self, op_id):
        # English: Removes a single operation from the bottom bar
        # Español: Elimina una operación concreta de la barra inferior
        if op_id is None:
            return
        self.operation_bar.finish(op_id)
        self._sync_buttons_state()

    def _close_progress_dialog(self, op_id=None):
        # English: Closes one operation, or all of them when no id is given
        # Español: Cierra una operación, o todas si no se indica identificador
        if op_id is None:
            self.operation_bar.finish_all()
        else:
            self.operation_bar.finish(op_id)

    def _show_progress(self, message, skip_callback=None, cancel_token=None):
        # English: Starts a new operation and returns its id. Every operation
        # has its own row, so concurrent installs do not cancel each other.
        # Español: Inicia una operación nueva y devuelve su identificador.
        # Cada operación tiene su propia fila, así las instalaciones
        # simultáneas no se anulan entre sí.
        op_id = None

        def _on_cancel():
            self._cancel_operation(op_id, cancel_token)

        op_id = self.operation_bar.start(
            message,
            skip_callback=skip_callback,
            cancel_callback=_on_cancel if cancel_token is not None else None,
        )
        self._last_operation_id = op_id
        return op_id

    def _sync_buttons_state(self):
        # English: Buttons are only restored when no operation is running
        # Español: Los botones solo se reactivan si no queda ninguna operación
        if not self.operation_bar.has_operations():
            self.set_buttons_sensitive(True)

    def update_progress_ui(self):
        # English: The bottom bars pulse on their own timer now
        # Español: Las barras inferiores ahora laten solas con su temporizador
        new_val = min(1.0, self.progress_bar.get_fraction() + 0.01)
        self.progress_bar.set_fraction(new_val)
        return False

    def _answer_package_question(self, question, default_yes, yes_letter, no_letter):
        """Popup con dos botones para una pregunta del gestor de paquetes.

        Se llama desde el hilo de la operación y bloquea hasta que el usuario
        responda. Devuelve True/False, o None para usar la respuesta por
        defecto (si nadie contesta o el diálogo se cierra).
        """
        done = threading.Event()
        result = {'yes': None}

        def _on_response(dialog, response):
            result['yes'] = (response == 'yes')
            done.set()

        def _show():
            try:
                dialog = Adw.AlertDialog(
                    heading=_("El instalador te hace una pregunta"),
                    body=question
                )
                dialog.add_response("no", _("No ({})").format(no_letter.upper()))
                dialog.add_response("yes", _("Sí ({})").format(yes_letter.upper()))
                dialog.set_default_response("yes" if default_yes else "no")
                if default_yes:
                    dialog.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
                else:
                    dialog.set_response_appearance("no", Adw.ResponseAppearance.SUGGESTED)
                dialog.connect("response", _on_response)
                dialog.present(self)
            except Exception:
                # English: No popup possible -> keep the default answer
                # Español: sin popup posible -> se mantiene la respuesta por defecto
                result['yes'] = None
                done.set()
            return False

        GLib.idle_add(_show)
        # English: If the popup is closed without answering, keep the default
        # (the thread cannot know the dialog was dismissed, hence the timeout)
        # Español: si el popup se cierra sin responder, se mantiene la opción
        # por defecto (el hilo no puede saber que el diálogo se cerró)
        if not done.wait(timeout=60):
            return None
        return result['yes']

    def _present_result_dialog(self, dialog, is_error, log_text=""):
        # English: On failure, offer viewing detailed logs and reopening in a terminal
        # Español: ante un fallo, ofrecer ver los registros detallados y reabrir en una terminal
        if is_error:
            if log_text:
                dialog._log_text = str(log_text)
                dialog.add_response("logs", _("Ver detalles del registro"))
            if prompt_engine.get_last_failure():
                dialog.add_response("terminal", _("Abrir en una terminal"))
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", self._on_result_dialog_response)
        dialog.present(self)

    def _on_result_dialog_response(self, dialog, response):
        if response == "terminal":
            open_last_failure_in_terminal()
        elif response == "logs":
            self._show_error_log_dialog(getattr(dialog, "_log_text", ""))

    def _show_error_log_dialog(self, log_text):
        if not log_text:
            return
        log_win = Adw.Window(transient_for=self, modal=True)
        log_win.set_title(_("Detalles del error / Registro"))
        log_win.set_default_size(680, 420)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_monospace(True)
        buffer = text_view.get_buffer()
        buffer.set_text(log_text)
        scroll.set_child(text_view)
        box.append(scroll)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        
        copy_btn = Gtk.Button(label=_("Copiar registro"))
        def _on_copy(b):
            try:
                cb = Gdk.Display.get_default().get_clipboard()
                cb.set(log_text)
                copy_btn.set_label(_("¡Copiado!"))
            except Exception:
                pass
        copy_btn.connect("clicked", _on_copy)
        btn_box.append(copy_btn)
        
        close_btn = Gtk.Button(label=_("Cerrar"))
        close_btn.connect("clicked", lambda b: log_win.close())
        btn_box.append(close_btn)
        
        box.append(btn_box)
        log_win.set_content(box)
        log_win.present()

    def on_installation_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)

        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error en la instalación!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He terminado la instalación"), body=message)
        
        self._present_result_dialog(dialog, is_error, log_text=stderr_output or message)
        self._sync_buttons_state()

    def on_uninstall_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)

        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error en la desinstalación!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("Desinstalación completada"), body=message)
        
        self._present_result_dialog(dialog, is_error, log_text=stderr_output or message)
        self._sync_buttons_state()
        if self.file_path and self.main_stack.get_visible_child_name() == "package_details":
            GLib.idle_add(lambda: self.show_package_details(identifier=self.file_path, is_local=False))

    def on_fix_deps_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)

        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error al corregir las dependencias!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He corregido las dependencias"), body=message)
        
        self._present_result_dialog(dialog, is_error, log_text=stderr_output or message)
        self._sync_buttons_state()

    def on_upgrade_system_complete(self, message, is_error=False, stderr_output=""):
        # English: Handle system upgrade completion dialog and state reset
        # Español: Manejar el diálogo de finalización de actualización del sistema y reinicio de estado
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)

        if is_error:
            dialog = Adw.AlertDialog(heading=_("¡Un error al actualizar el sistema!"), body=message)
        else:
            dialog = Adw.AlertDialog(heading=_("He terminado de actualizar el sistema"), body=message)
        
        self._present_result_dialog(dialog, is_error, log_text=stderr_output or message)
        self._sync_buttons_state()

    def set_buttons_sensitive(self, sensitive):
        for attr in ('install_button', 'fix_deps_button', 'pwa_button', 'upgrade_system_button'):
            btn = getattr(self, attr, None)
            if btn:
                btn.set_sensitive(sensitive)

    def check_updates_on_startup(self):
        thread = threading.Thread(target=self.check_updates_thread)
        thread.daemon = True
        thread.start()
        return False

    def check_updates_thread(self):
        try:
            result = self.update_service.check_for_updates()
            if result and result[0]:
                GLib.idle_add(self.show_update_dialog, result[1], result[2])
        except Exception:
            pass

    def show_update_dialog(self, latest_version, release_url):
        dialog = UpdateDialog(self, latest_version, release_url)
        dialog.connect("response", self.on_update_dialog_response)
        dialog.present()

    def on_update_dialog_response(self, dialog, response):
        if response == "update":
            safe_open_url(getattr(dialog, "release_url", "https://github.com/InledGroup/appinstall/releases/latest"))
        dialog.close()

    def on_check_updates_clicked(self, button):
        self.status_label.set_text(_("Estoy comprobando las actualizaciones"))
        def _check():
            try:
                result = self.update_service.check_for_updates()
                if result and result[0]:
                    GLib.idle_add(self.show_update_dialog, result[1], result[2])
                else:
                    GLib.idle_add(self.show_up_to_date_dialog)
            except Exception as e:
                GLib.idle_add(self.show_update_error)
        
        threading.Thread(target=_check, daemon=True).start()

    def show_up_to_date_dialog(self):
        dialog = Adw.AlertDialog(
            heading=_("Estoy actualizado :)"),
            body=_("Bien hecho, estoy actualizado a la última versión ({}).").format(CURRENT_VERSION)
        )
        dialog.add_response("ok", _("Aceptar"))
        dialog.set_default_response("ok")
        dialog.present(self)
        self.status_label.set_text(_("Estoy actualizado :)"))

    def show_update_error(self):
        dialog = Adw.AlertDialog(
            heading=_("He encontrado un error"),
            body=_("Vaya, no he podido comprobar las actualizaciones. ¿Estás conectado a internet?")
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        return False

    def on_package_name_changed(self, entry):
        text = entry.get_text()
        stripped_text = text.strip()

        # Sync back to sidebar entry
        if hasattr(self, 'sidebar_search_entry') and self.sidebar_search_entry.get_text() != text:
            self.sidebar_search_entry.set_text(text)

        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None
        
        if len(stripped_text) >= 3:
            self.search_timer = GLib.timeout_add(30, self.perform_package_search, stripped_text)
        else:
            child = self.search_results_list.get_first_child()
            while child:
                self.search_results_list.remove(child)
                child = self.search_results_list.get_first_child()

    def perform_package_search(self, query):
        self.search_timer = None
        self.search_spinner.set_visible(True)
        self.search_spinner.start()

        def _search():
            results = []
            
            # Formulate variations of the query in the background
            queries = [query]
            if ' ' in query:
                queries.append(query.replace(' ', '-'))
                queries.append(query.replace(' ', ''))
            
            seen = set()
            for q in queries:
                if self.search_service:
                    q_results = self.search_service.search(q)
                else:
                    q_results = []
                    try:
                        raw_results = self.pkg_manager.search(q)[:15]
                        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                        for res in raw_results:
                            if theme.has_icon(res['name']):
                                res['icon'] = res['name']
                            elif theme.has_icon(res['name'].split('-')[0]):
                                res['icon'] = res['name'].split('-')[0]
                            q_results.append(res)
                    except:
                        pass
                    
                    if HAS_BREW:
                        try:
                            brew_output = subprocess.check_output([BREW_PATH, 'search', q], timeout=10, stderr=subprocess.STDOUT).decode('utf-8')
                            for line in brew_output.split('\n')[:15]:
                                if line.strip() and not line.startswith('=='):
                                    name = line.strip()
                                    q_results.append({
                                        'name': name,
                                        'display_name': name,
                                        'desc': _("Fórmula de Homebrew"),
                                        'source': 'brew',
                                        'icon': 'system-software-install-symbolic'
                                    })
                        except:
                            pass
                
                # Merge and deduplicate
                for res in q_results:
                    key = (res.get('name'), res.get('source'))
                    if key not in seen:
                        seen.add(key)
                        results.append(res)
                        
            GLib.idle_add(self.show_search_results, results)
            
        threading.Thread(target=_search, daemon=True).start()
        return False
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
            box.set_hexpand(True)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            
            icon_val = res.get('icon', '')
            source = res.get('source', 'system')
            fallback_icon = "package-x-generic-symbolic" if source in ['apt', 'dnf', 'pacman'] else "system-software-install-symbolic"
            from src.utils.system import create_app_icon_widget
            icon_widget = create_app_icon_widget(icon_val, size=36, fallback=fallback_icon, package_id=res.get('name', 'app'))
            box.append(icon_widget)
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_hexpand(True)
            name_label = Gtk.Label(label=res.get('display_name', res['name']), xalign=0)
            name_label.set_ellipsize(Pango.EllipsizeMode.END)
            name_label.set_hexpand(True)
            name_label.add_css_class("title-label") 
            vbox.append(name_label)
            
            desc_label = Gtk.Label(label=res['desc'], xalign=0)
            desc_label.set_ellipsize(Pango.EllipsizeMode.END)
            desc_label.set_hexpand(True)
            desc_label.add_css_class("subtitle-label")
            vbox.append(desc_label)
            
            box.append(vbox)
            
            # Tag/badge representing package source
            source = res.get('source', 'system')
            if source in ['apt', 'dnf', 'pacman', 'system']:
                source_label = _("Nativo")
                badge_class = "badge-system"
            elif source == 'flatpak':
                source_label = "Flatpak"
                badge_class = "badge-flatpak"
            elif source == 'pulsar':
                source_label = "Pulsar Store"
                badge_class = "badge-pulsar"
            elif source == 'gnome-extension':
                source_label = _("Extensión GNOME")
                badge_class = "badge-generic"
            elif source == 'snap':
                source_label = "Snap"
                badge_class = "badge-snap"
            elif source == 'aur':
                source_label = "AUR"
                badge_class = "badge-aur"
            elif source == 'brew':
                source_label = "Brew"
                badge_class = "badge-brew"
            else:
                source_label = source.capitalize()
                badge_class = "badge-generic"

            badge = Gtk.Label(label=source_label)
            badge.add_css_class("badge")
            badge.add_css_class(badge_class)
            badge.set_valign(Gtk.Align.CENTER)
            box.append(badge)
            
            # App Store style "Ver" button on the right
            ver_btn = Gtk.Button(label=_("Ver"))
            ver_btn.add_css_class("app-card-button")
            ver_btn.set_valign(Gtk.Align.CENTER)
            ver_btn.set_margin_start(8)
            ver_btn.connect("clicked", lambda b, r=row: self.on_search_result_activated(self.search_results_list, r))
            box.append(ver_btn)
            
            row.set_child(box)
            row.pkg_name = res['name']
            row.source = res['source']
            self.search_results_list.append(row)

    def on_search_result_activated(self, listbox, row):
        pkg_name = row.pkg_name
        if row.source == 'gnome-extension' or row.source == 'gnome-ext':
            pkg_name = f"gnome-ext:{pkg_name}"
        elif row.source == 'brew':
            pkg_name = f"brew:{pkg_name}"
        elif row.source == 'flatpak':
            pkg_name = f"flatpak:{pkg_name}"
        elif row.source == 'snap':
            pkg_name = f"snap:{pkg_name}"
        elif row.source == 'aur':
            pkg_name = f"aur:{pkg_name}"
        elif row.source == 'pulsar':
            pkg_name = f"pulsar:{pkg_name}"
            
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None
            
        self.file_path = pkg_name
        # Mostrar detalles antes de instalar, pasándole el paquete seleccionado directamente
        self.show_package_details(identifier=pkg_name, is_local=False)

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

    def on_search_priority_clicked(self, btn):
        if hasattr(self, 'menu_popover') and self.menu_popover:
            self.menu_popover.popdown()
        dialog = SearchPriorityDialog(self, self.search_service)
        dialog.present()


class SearchPriorityDialog(Adw.Window):
    def __init__(self, parent, search_service):
        super().__init__(transient_for=parent, modal=True)
        self.search_service = search_service
        self.set_default_size(380, 280)
        self.add_css_class("main-window")
        
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Prioridad de Búsqueda")))
        header_bar.add_css_class("header-bar")
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(main_box)
        self.set_content(toolbar_view)
        
        info_label = Gtk.Label(label=_("Elige qué origen de paquetes prefieres ver primero en las búsquedas:"), xalign=0)
        info_label.set_wrap(True)
        main_box.append(info_label)
        
        # Cargar prioridad actual
        current_priority = self.search_service.priority_order
        first_pref = current_priority[0] if current_priority else "system"
        
        # Radio buttons (Gtk.CheckButton en GTK4 agrupados)
        self.radio_system = Gtk.CheckButton(label=_("Nativo (Sistema: APT/DNF/Pacman)"))
        self.radio_system.set_active(first_pref == "system")
        main_box.append(self.radio_system)
        
        self.radio_flatpak = Gtk.CheckButton(label=_("Flatpak (Flathub)"))
        self.radio_flatpak.set_group(self.radio_system)
        self.radio_flatpak.set_active(first_pref == "flatpak")
        main_box.append(self.radio_flatpak)
        
        self.radio_snap = Gtk.CheckButton(label=_("Snap Store"))
        self.radio_snap.set_group(self.radio_system)
        self.radio_snap.set_active(first_pref == "snap")
        main_box.append(self.radio_snap)
        
        self.radio_aur = Gtk.CheckButton(label=_("AUR (Arch User Repository)"))
        self.radio_aur.set_group(self.radio_system)
        self.radio_aur.set_active(first_pref == "aur")
        main_box.append(self.radio_aur)
        
        # Botones de acción
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)
        
        cancel_btn = Gtk.Button(label=_("Cancelar"))
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_box.append(cancel_btn)
        
        save_btn = Gtk.Button(label=_("Guardar"))
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self.on_save_clicked)
        btn_box.append(save_btn)
        
        main_box.append(btn_box)
        
    def on_save_clicked(self, btn):
        # Determinar selección
        if self.radio_system.get_active():
            selection = "system"
        elif self.radio_flatpak.get_active():
            selection = "flatpak"
        elif self.radio_snap.get_active():
            selection = "snap"
        elif self.radio_aur.get_active():
            selection = "aur"
        else:
            selection = "system"
            
        # Reordenar prioridad: el seleccionado primero, y luego los otros en orden por defecto
        default_order = ["system", "flatpak", "snap", "aur"]
        new_order = [selection]
        for s in default_order:
            if s != selection:
                new_order.append(s)
                
        # Guardar en SearchService
        self.search_service.save_priority_order(new_order)
        self.close()
