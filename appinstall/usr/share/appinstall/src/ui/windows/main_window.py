import os
import threading
import subprocess
import requests
from gi.repository import Gtk, GLib, Adw, Gdk, Pango
from src.infrastructure.services.localization import _
from src.utils.constants import CURRENT_VERSION
from src.utils.system import get_safe_window_size, safe_open_url, has_internet, HAS_BREW, BREW_PATH
from src.ui.components.update_dialog import UpdateDialog

# Import other windows
from .installed_apps_window import InstalledAppsWidget
from .cleanup_window import SystemCleanupWidget
from .antivirus_window import AntivirusWidget
from .pwa_config_window import PWAConfigWindow
from .appimage_config_window import AppImageConfigWindow
from .progress_window import ProgressWindow
from .package_details_window import PackageDetailsWidget

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
        self.file_path = file_to_open
        
        self.set_title("App Install")
        self.set_icon_name("es.inled.AppInstall")

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
        self.set_content(main_layout)

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
        self.content_stack = Adw.ViewStack()
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)
        main_layout.append(self.content_stack)

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

        # 1. Installed Apps Widget
        uninstall_service = UninstallService(self.pkg_manager)
        self.installed_apps_widget = InstalledAppsWidget(self, self.pkg_manager, uninstall_service)
        self.content_stack.add_named(self.installed_apps_widget, "installed")

        # 2. Updates Widget
        self.updates_widget = self.setup_updates_widget()
        self.content_stack.add_named(self.updates_widget, "updates")

        # 3. Cleanup Widget
        cleanup_service = CleanupService(self.pkg_manager)
        self.cleanup_widget = SystemCleanupWidget(self, cleanup_service)
        self.content_stack.add_named(self.cleanup_widget, "cleanup")

        # 4. Antivirus Widget
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
        
        # 1. Apps imprescindibles Section (from Flathub)
        self.popular_section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        popular_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        popular_title = Gtk.Label(label=_("Apps imprescindibles"), xalign=0)
        popular_title.add_css_class("store-section-title")
        popular_header.append(popular_title)
        self.popular_section_box.append(popular_header)
        
        self.popular_grid = Gtk.Grid()
        self.popular_grid.set_column_spacing(24)
        self.popular_grid.set_row_spacing(16)
        self.popular_grid.set_column_homogeneous(True)
        self.popular_section_box.append(self.popular_grid)
        self.main_box.append(self.popular_section_box)
        
        self.popular_spinner = Gtk.Spinner()
        self.popular_spinner.set_size_request(24, 24)
        self.popular_spinner.set_halign(Gtk.Align.CENTER)
        self.popular_spinner.start()
        self.popular_section_box.append(self.popular_spinner)
        
        # 2. Lo mejor de la semana Section (from Flathub)
        self.trending_section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        trending_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        trending_title = Gtk.Label(label=_("Lo mejor de la semana"), xalign=0)
        trending_title.add_css_class("store-section-title")
        trending_header.append(trending_title)
        self.trending_section_box.append(trending_header)
        
        self.trending_grid = Gtk.Grid()
        self.trending_grid.set_column_spacing(24)
        self.trending_grid.set_row_spacing(16)
        self.trending_grid.set_column_homogeneous(True)
        self.trending_section_box.append(self.trending_grid)
        self.main_box.append(self.trending_section_box)
        
        self.trending_spinner = Gtk.Spinner()
        self.trending_spinner.set_size_request(24, 24)
        self.trending_spinner.set_halign(Gtk.Align.CENTER)
        self.trending_spinner.start()
        self.trending_section_box.append(self.trending_spinner)
        
        # 3. Top apps gratis Section (from Flathub)
        self.top_free_section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        top_free_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top_free_title = Gtk.Label(label=_("Top apps gratis"), xalign=0)
        top_free_title.add_css_class("store-section-title")
        top_free_header.append(top_free_title)
        self.top_free_section_box.append(top_free_header)
        
        scrolled_top_free = Gtk.ScrolledWindow()
        scrolled_top_free.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.top_free_horizontal_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.top_free_horizontal_box.set_margin_top(8)
        self.top_free_horizontal_box.set_margin_bottom(8)
        scrolled_top_free.set_child(self.top_free_horizontal_box)
        self.top_free_section_box.append(scrolled_top_free)
        self.main_box.append(self.top_free_section_box)
        
        self.top_free_spinner = Gtk.Spinner()
        self.top_free_spinner.set_size_request(24, 24)
        self.top_free_spinner.set_halign(Gtk.Align.CENTER)
        self.top_free_spinner.start()
        self.top_free_section_box.append(self.top_free_spinner)
        
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
            # Switch to "store" tab if not already there
            store_row = self.sidebar_list.get_row_at_index(0)
            if self.sidebar_list.get_selected_row() != store_row:
                self.sidebar_list.select_row(store_row)
                
            self.header_stack.set_visible_child_name("search")
            self.main_stack.set_visible_child_name("search_results")
            
            stripped_text = text.strip()
            if len(stripped_text) >= 3:
                if self.search_timer:
                    GLib.source_remove(self.search_timer)
                self.search_timer = GLib.timeout_add(30, self.perform_package_search, stripped_text)
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
            self.header_stack.set_visible_child_name("search")
            self.main_stack.set_visible_child_name("search_results")
            if len(text) >= 3:
                self.perform_package_search(text)

    def load_store_recommendations(self):
        def _fetch():
            if not self.search_service:
                return

            if not has_internet():
                GLib.idle_add(self.show_offline_banner)
                return

            try:
                # Fetch popular apps (17 total, to use 12 for popular, 5 for top free)
                popular_all = self.search_service.get_popular_apps(limit=17)
                popular = popular_all[:12]
                top_free = popular_all[12:17] if len(popular_all) > 12 else popular_all[:5]

                # Fetch trending apps (12)
                trending = self.search_service.get_trending_apps(limit=12)
            except Exception as e:
                print(f"Error loading store recommendations: {e}")
                popular_all = []
                trending = []

            if not popular_all and not trending:
                GLib.idle_add(self.show_offline_banner)
            else:
                GLib.idle_add(self.populate_recommendations, popular, trending, top_free)

        threading.Thread(target=_fetch, daemon=True).start()

    def _stop_recommendation_spinners(self):
        # English: Stop and remove the loading spinners of the store sections
        # Español: Detener y quitar los indicadores de carga de las secciones de la tienda
        if hasattr(self, 'popular_spinner') and self.popular_spinner:
            try:
                self.popular_spinner.stop()
                self.popular_section_box.remove(self.popular_spinner)
            except: pass

        if hasattr(self, 'trending_spinner') and self.trending_spinner:
            try:
                self.trending_spinner.stop()
                self.trending_section_box.remove(self.trending_spinner)
            except: pass

        if hasattr(self, 'top_free_spinner') and self.top_free_spinner:
            try:
                self.top_free_spinner.stop()
                self.top_free_section_box.remove(self.top_free_spinner)
            except: pass

    def show_offline_banner(self):
        # English: Show the offline warning on the home screen
        # Español: Mostrar el aviso de modo sin conexión en la pantalla de inicio
        self._stop_recommendation_spinners()
        if hasattr(self, 'offline_banner'):
            self.offline_banner.set_visible(True)

    def populate_recommendations(self, popular, trending, top_free):
        # Stop and remove spinners if they exist
        self._stop_recommendation_spinners()
            
        # Populate popular (4 rows, 3 columns)
        for idx, app in enumerate(popular[:12]):
            row = idx % 4
            col = idx // 4
            item_widget = self.create_app_grid_item(app)
            self.popular_grid.attach(item_widget, col, row, 1, 1)
            
        # Populate trending (4 rows, 3 columns)
        for idx, app in enumerate(trending[:12]):
            row = idx % 4
            col = idx // 4
            item_widget = self.create_app_grid_item(app)
            self.trending_grid.attach(item_widget, col, row, 1, 1)
            
        # Populate top free (5 items side by side)
        for idx, app in enumerate(top_free[:5]):
            card = self.create_top_free_card(idx + 1, app)
            self.top_free_horizontal_box.append(card)

    def create_app_grid_item(self, app_data):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.add_css_class("store-app-card")
        box.set_hexpand(True)
        box.set_valign(Gtk.Align.CENTER)
        
        # Rounded App Icon
        icon_path = app_data.get('icon', '')
        if icon_path and os.path.exists(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
        icon.set_pixel_size(48)
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
        ver_btn.connect("clicked", lambda b: self.on_recommendation_clicked(app_data))
        box.append(ver_btn)
        
        # Connect click gesture to the box to open install page from anywhere on the card
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", lambda g, n, x, y: self.on_recommendation_clicked(app_data))
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
        ver_btn.connect("clicked", lambda b: self.on_recommendation_clicked(app_data))
        card.append(ver_btn)
        
        # Make the entire top-free card clickable
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", lambda g, n, x, y: self.on_recommendation_clicked(app_data))
        card.add_controller(click_gesture)
        
        return card

    def on_recommendation_clicked(self, app_data):
        pkg_name = app_data['name']
        if app_data.get('source') == 'flatpak':
            pkg_name = f"flatpak:{pkg_name}"
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

    def trigger_updates_check(self):
        self.updates_spinner.start()
        self.updates_spinner.set_visible(True)
        self.updates_status_label.set_text(_("Comprobando actualizaciones..."))
        self.upgrade_all_btn.set_sensitive(False)
        
        child = self.updates_listbox.get_first_child()
        while child:
            self.updates_listbox.remove(child)
            child = self.updates_listbox.get_first_child()

        def _check():
            try:
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
                    import shutil
                    if shutil.which('pacman'):
                        try:
                            output = subprocess.check_output(['pacman', '-Qu'], stderr=subprocess.DEVNULL, timeout=10).decode('utf-8')
                            for line in output.split('\n'):
                                if line.strip():
                                    parts = line.split()
                                    if len(parts) >= 2:
                                        upgradable_pkgs.append(parts[0])
                        except subprocess.CalledProcessError as e:
                            # pacman -Qu returns 1 if there are no updates. That is normal behavior.
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
                            # dnf check-update returns 100 if updates exist, 0 if not, 1 if error
                            res = subprocess.run(['dnf', 'check-update', '-q'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
                            if res.returncode in [0, 100]:
                                output = res.stdout.decode('utf-8')
                                for line in output.split('\n'):
                                    if line.strip():
                                        parts = line.split()
                                        if len(parts) >= 2 and parts[0] != 'Obtaining':
                                            upgradable_pkgs.append(parts[0])
                            else:
                                print(f"dnf check-update returned code: {res.returncode}")
                        except Exception as e:
                            print(f"dnf check-updates error: {e}")
                except Exception as e:
                    print(f"Error checking system updates: {e}")
                    
                GLib.idle_add(self.show_updates_results, appinstall_upgradable, latest_app_version, upgradable_pkgs)
            except Exception as e:
                print(f"Error in updates check thread: {e}")
                GLib.idle_add(self.show_updates_error)
                
        threading.Thread(target=_check, daemon=True).start()

    def show_updates_results(self, appinstall_upgradable, latest_app_version, upgradable_pkgs):
        self.updates_spinner.stop()
        self.updates_spinner.set_visible(False)
        
        total_updates = len(upgradable_pkgs) + (1 if appinstall_upgradable else 0)
        
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
                
            for pkg in upgradable_pkgs[:100]:
                self.add_update_row(pkg, _("Actualización disponible de los repositorios del sistema"))
                
            if len(upgradable_pkgs) > 100:
                self.add_update_row("...", _("Y {} actualizaciones más...").format(len(upgradable_pkgs) - 100))

    def add_update_row(self, name, description, is_app=False):
        row = Gtk.ListBoxRow()
        row.add_css_class("list-row")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8); box.set_margin_bottom(8)
        box.set_margin_start(8); box.set_margin_end(8)
        
        icon = Gtk.Image.new_from_icon_name("es.inled.AppInstall" if is_app else "package-x-generic-symbolic")
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
            is_scheme = any(self.file_path.startswith(prefix) for prefix in ["flatpak:", "snap:", "aur:", "brew:", "appstream:", "flatpak+https:"])
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
            
        self.status_label.set_text(_("Obteniendo información de la aplicación..."))
        self.progress_dialog = ProgressWindow(self, _("Analizando paquete..."), skip_callback=self.on_skip_analysis_clicked)
        self.progress_dialog.present()
        
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
        
        if hasattr(self, 'details_widget_instance') and self.details_widget_instance:
            try:
                self.main_stack.remove(self.details_widget_instance)
            except: pass
            
        prev_view = self.main_stack.get_visible_child_name()
        if prev_view not in ['menu', 'search_results']:
            prev_view = 'menu'
        self.details_prev_view = prev_view
            
        self.details_widget_instance = PackageDetailsWidget(
            self, 
            info, 
            on_install_callback=lambda: self.on_install_clicked(None),
            on_uninstall_callback=lambda: self.uninstall_package_from_details(info.get('name'), info.get('source')),
            back_callback=self.on_details_back_clicked
        )
        self.main_stack.add_named(self.details_widget_instance, "details")
        self.main_stack.set_visible_child_name("details")
        # Show the details toolbar (with close button) instead of hiding the header
        self.details_title_label.set_text(info.get('name', ''))
        self.header_stack.set_visible(True)
        self.header_stack.set_visible_child_name("details")

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

    def on_skip_analysis_clicked(self):
        # English: Skip package analysis and trigger installation directly
        # Español: Omitir el análisis del paquete e iniciar la instalación de inmediato
        self.progress_dialog = None
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
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_size_request(-1, 300)
            view = Gtk.TextView()
            view.set_editable(False)
            view.set_cursor_visible(False)
            view.add_css_class("pkgbuild-view")
            view.get_buffer().set_text(pkgbuild)
            scrolled.set_child(view)
            dialog.set_extra_child(scrolled)
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("install", _("Instalar"))
        dialog.set_default_response("cancel")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_aur_confirm_response)
        dialog.present(self)

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
        
        self._show_progress(_("Instalando..."))
        
        self.install_service.run_installation(cmd, self.file_path, self.update_progress_ui, self.on_installation_complete, on_log=self.on_operation_log)

    def on_fix_deps_clicked(self, widget):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Corregir errores"))
        self.progress_bar.set_fraction(0.0)
        
        self._show_progress(_("Corregir errores"))
        
        cmd = self.pkg_manager.fix_broken()
        self.install_service.run_fix_deps(cmd, self.update_progress_ui, self.on_fix_deps_complete, on_log=self.on_operation_log)

    def on_upgrade_system_clicked(self, widget):
        # English: Trigger full system update and upgrade
        # Español: Desencadenar la actualización completa del sistema
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Actualizando el sistema..."))
        self.progress_bar.set_fraction(0.0)
        
        self._show_progress(_("Actualizando el sistema..."))
        
        cmd = self.pkg_manager.upgrade_system()
        self.install_service.run_installation(cmd, "system_upgrade", self.update_progress_ui, self.on_upgrade_system_complete, on_log=self.on_operation_log)

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
        
        self._show_progress(_("Instalando {}...").format(display_name))
        
        cmd = self.install_service.get_appimage_install_command(self.file_path, display_name, icon_path)
        self.install_service.run_installation(cmd, self.file_path, self.update_progress_ui, self.on_installation_complete, on_log=self.on_operation_log)

    def proceed_with_pwa_installation(self, display_name, url, icon_path):
        self.set_buttons_sensitive(False)
        self.status_label.set_text(_("Creando PWA..."))
        self.progress_bar.set_fraction(0.0)
        
        self._show_progress(_("Creando PWA {}...").format(display_name))
        
        cmd = self.install_service.get_pwa_install_command(display_name, url, icon_path)
        self.install_service.run_installation(cmd, None, self.update_progress_ui, self.on_installation_complete, on_log=self.on_operation_log)

    def on_operation_log(self, line):
        # English: Append a line to the operation log shown in the progress window
        # Español: Añadir una línea al registro de operación mostrado en la ventana de progreso
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.append_log(line)

    def _close_progress_dialog(self):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            try:
                self.progress_dialog.close()
            except Exception:
                pass
            self.progress_dialog = None

    def _show_progress(self, message, skip_callback=None):
        self._close_progress_dialog()
        self.progress_dialog = ProgressWindow(self, message, skip_callback=skip_callback)
        self.progress_dialog.present()
        return self.progress_dialog

    def update_progress_ui(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.01)
        self.progress_bar.set_fraction(new_value)
        return False

    def on_installation_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        
        if is_error:
            # English: Keep the log window open so the user can inspect the output
            # Español: Mantener abierta la ventana de registro para que el usuario inspeccione la salida
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.auto_show_log()
            dialog = Adw.AlertDialog(heading=_("¡Un error en la instalación!"), body=message)
        else:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
            dialog = Adw.AlertDialog(heading=_("He terminado la instalación"), body=message)
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)
        self.set_buttons_sensitive(True)

    def on_fix_deps_complete(self, message, is_error=False):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        if is_error:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.auto_show_log()
            dialog = Adw.AlertDialog(heading=_("¡Un error al corregir las dependencias!"), body=message)
        else:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
            dialog = Adw.AlertDialog(heading=_("He corregido las dependencias"), body=message)
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)
        self.set_buttons_sensitive(True)

    def on_upgrade_system_complete(self, message, is_error=False, stderr_output=""):
        # English: Handle system upgrade completion dialog and state reset
        # Español: Manejar el diálogo de finalización de actualización del sistema y reinicio de estado
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        
        if is_error:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.auto_show_log()
            dialog = Adw.AlertDialog(heading=_("¡Un error al actualizar el sistema!"), body=message)
        else:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
            dialog = Adw.AlertDialog(heading=_("He terminado de actualizar el sistema"), body=message)
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)
        self.set_buttons_sensitive(True)

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
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            
            icon_val = res.get('icon', '')
            if icon_val and os.path.exists(icon_val):
                icon = Gtk.Image.new_from_file(icon_val)
            else:
                icon_name = icon_val
                if not icon_name or (not theme.has_icon(icon_name) and not os.path.isabs(icon_name)):
                    icon_name = "package-x-generic-symbolic" if res.get('source') in ['apt', 'dnf', 'pacman'] else "system-software-install-symbolic"
                icon = Gtk.Image.new_from_icon_name(icon_name)
            
            icon.set_pixel_size(32)
            box.append(icon)
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_hexpand(True)
            name_label = Gtk.Label(label=res.get('display_name', res['name']), xalign=0)
            name_label.add_css_class("title-label") 
            vbox.append(name_label)
            
            desc_label = Gtk.Label(label=res['desc'], xalign=0)
            desc_label.set_ellipsize(Pango.EllipsizeMode.END)
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
        if row.source == 'brew':
            pkg_name = f"brew:{pkg_name}"
        elif row.source == 'flatpak':
            pkg_name = f"flatpak:{pkg_name}"
        elif row.source == 'snap':
            pkg_name = f"snap:{pkg_name}"
        elif row.source == 'aur':
            pkg_name = f"aur:{pkg_name}"
            
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
