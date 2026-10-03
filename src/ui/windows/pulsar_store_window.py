import os
import threading
from gi.repository import Gtk, GLib, Adw, Pango
from src.infrastructure.services.localization import _
from src.infrastructure.adapters.pulsar_store_adapter import PulsarStoreAdapter
from src.utils.system import get_cached_icon, safe_open_url

class PulsarStoreWidget(Gtk.Box):
    """Pulsar Store catalog browser and manager integrated into AppInstall."""

    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.main_window = main_window
        self.adapter = PulsarStoreAdapter()
        self.all_packages = []
        self.current_filter = "all"
        self.search_query = ""

        self.setup_ui()
        self.load_catalog_async()

    def setup_ui(self):
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(20)
        self.set_margin_end(20)

        # Header with Title and Refresh
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label=_("Pulsar Store"), xalign=0)
        title_lbl.add_css_class("store-section-title")
        sub_lbl = Gtk.Label(label=_("Explora aplicaciones, extensiones y módulos del ecosistema Pulsar OS"), xalign=0)
        sub_lbl.add_css_class("subtitle-label")
        title_box.append(title_lbl)
        title_box.append(sub_lbl)
        title_box.set_hexpand(True)
        header_box.append(title_box)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Actualizar catálogo"))
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda b: self.load_catalog_async(force=True))
        header_box.append(refresh_btn)

        self.append(header_box)

        # Filter & Search bar
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls_box.set_margin_top(4)
        controls_box.set_margin_bottom(4)

        # Category Filter Dropdown or Button Group
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        self.filter_buttons = {}
        categories = [
            ("all", _("Todos")),
            ("flatpak", _("Aplicaciones")),
            ("gnome_extension", _("Extensiones")),
            ("sayri_skill", _("Skills")),
            ("sayri_plugin", _("Plugins"))
        ]

        for cat_id, cat_name in categories:
            btn = Gtk.Button(label=cat_name)
            btn.add_css_class("pill")
            if cat_id == "all":
                btn.add_css_class("suggested-action")
            btn.connect("clicked", self._on_filter_clicked, cat_id)
            self.filter_buttons[cat_id] = btn
            filter_box.append(btn)

        controls_box.append(filter_box)

        # Search within Pulsar Store
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Buscar en Pulsar Store..."))
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        controls_box.append(self.search_entry)

        self.append(controls_box)

        # Main Scrolled Window with FlowBox
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(3)
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_row_spacing(12)
        self.flowbox.set_column_spacing(12)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_margin_top(8)
        self.flowbox.set_margin_bottom(16)

        scrolled.set_child(self.flowbox)
        self.append(scrolled)

        # Status / Loading spinner
        self.spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.spinner_box.set_valign(Gtk.Align.CENTER)
        self.spinner_box.set_halign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.status_lbl = Gtk.Label(label=_("Cargando catálogo de Pulsar Store..."))
        self.status_lbl.add_css_class("subtitle-label")
        self.spinner_box.append(self.spinner)
        self.spinner_box.append(self.status_lbl)
        self.spinner_box.set_visible(False)
        self.append(self.spinner_box)

    def _on_filter_clicked(self, button, cat_id):
        self.current_filter = cat_id
        for cid, btn in self.filter_buttons.items():
            if cid == cat_id:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")
        self.render_packages()

    def _on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.render_packages()

    def load_catalog_async(self, force=False):
        self.spinner_box.set_visible(True)
        self.spinner.start()
        self.flowbox.set_visible(False)

        def worker():
            pkgs = self.adapter._fetch_catalog(force=force)
            GLib.idle_add(self._on_catalog_loaded, pkgs)

        threading.Thread(target=worker, daemon=True).start()

    def _on_catalog_loaded(self, pkgs):
        self.spinner.stop()
        self.spinner_box.set_visible(False)
        self.flowbox.set_visible(True)
        self.all_packages = pkgs or []
        self.render_packages()

    def render_packages(self):
        # Clear existing children safely
        while True:
            child = self.flowbox.get_first_child()
            if not child:
                break
            self.flowbox.remove(child)

        filtered = []
        for pkg in self.all_packages:
            ptype = pkg.get("type", "")
            if self.current_filter != "all" and ptype != self.current_filter:
                continue

            name = pkg.get("name", "")
            desc = pkg.get("description", "")
            pkg_id = pkg.get("id", "")

            if self.search_query:
                if (self.search_query not in name.lower() and
                    self.search_query not in desc.lower() and
                    self.search_query not in pkg_id.lower()):
                    continue

            filtered.append(pkg)

        if not filtered:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty_box.set_valign(Gtk.Align.CENTER)
            empty_box.set_margin_top(48)
            empty_lbl = Gtk.Label(label=_("No se han encontrado elementos en esta categoría."))
            empty_lbl.add_css_class("title-label")
            empty_box.append(empty_lbl)
            self.flowbox.append(empty_box)
            return

        for pkg in filtered:
            card = self.create_package_card(pkg)
            self.flowbox.append(card)

    def create_package_card(self, pkg):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        card.set_size_request(260, -1)

        # Top row: Icon + Titles + Badge
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        # Icon
        icon_url = pkg.get("icon_url", "")
        pkg_id = pkg.get("id", "")
        icon_img = Gtk.Image()
        icon_img.set_pixel_size(44)
        icon_img.add_css_class("app-card-icon")

        if icon_url:
            cached_path = get_cached_icon(icon_url, f"pulsar_{pkg_id}")
            if cached_path and os.path.exists(cached_path):
                icon_img.set_from_file(cached_path)
            else:
                icon_img.set_from_icon_name("system-software-install-symbolic")
        else:
            icon_img.set_from_icon_name("system-software-install-symbolic")

        top_row.append(icon_img)

        # Info Box
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        name_lbl = Gtk.Label(label=pkg.get("name", pkg_id), xalign=0)
        name_lbl.add_css_class("app-card-title")
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(name_lbl)

        author_lbl = Gtk.Label(label=pkg.get("author", "Pulsar"), xalign=0)
        author_lbl.add_css_class("app-card-subtitle")
        author_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(author_lbl)

        top_row.append(info_box)

        # Type Badge
        ptype = pkg.get("type", "")
        type_labels = {
            "flatpak": ("Flatpak", "badge-flatpak"),
            "gnome_extension": ("Extensión", "badge-system"),
            "sayri_skill": ("Skill", "badge-pulsar"),
            "sayri_plugin": ("Plugin", "badge-aur"),
        }
        lbl_text, badge_cls = type_labels.get(ptype, (ptype.capitalize(), "badge-generic"))
        badge = Gtk.Label(label=lbl_text)
        badge.add_css_class("badge")
        badge.add_css_class(badge_cls)
        badge.set_valign(Gtk.Align.START)
        top_row.append(badge)

        card.append(top_row)

        # Description
        desc_lbl = Gtk.Label(label=pkg.get("description", ""), xalign=0)
        desc_lbl.add_css_class("subtitle-label")
        desc_lbl.set_wrap(True)
        desc_lbl.set_max_lines(2)
        desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        desc_lbl.set_vexpand(True)
        card.append(desc_lbl)

        # Action Bottom Row
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_margin_top(4)

        ver_lbl = Gtk.Label(label=f"v{pkg.get('version', '1.0')}", xalign=0)
        ver_lbl.add_css_class("subtitle-label")
        ver_lbl.set_hexpand(True)
        action_row.append(ver_lbl)

        install_btn = Gtk.Button(label=_("Obtener"))
        install_btn.add_css_class("app-card-button")
        install_btn.connect("clicked", self._on_install_clicked, pkg)
        action_row.append(install_btn)

        card.append(action_row)
        return card

    def _on_install_clicked(self, button, pkg):
        pkg_id = pkg.get("id", "")
        pkg_type = pkg.get("type", "")
        
        if pkg_type == "flatpak":
            self.main_window.install_package(pkg_id, source="flatpak")
        elif pkg_type == "gnome_extension":
            # Direct GNOME extension install or scheme open
            safe_open_url(f"pulsar://install/{pkg_id}")
        else:
            safe_open_url(f"pulsar://install/{pkg_id}")
