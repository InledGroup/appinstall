import os
import re
import json
import shutil
import urllib.request
import subprocess
import threading
from gi.repository import Gtk, GLib, Adw, Pango, Gio
from src.infrastructure.services.localization import _
from src.utils.system import get_cached_icon, safe_open_url

def is_gnome_desktop() -> bool:
    """Check if currently running within a GNOME desktop environment."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    session = os.environ.get("DESKTOP_SESSION", "").upper()
    if any(k in desktop for k in ["GNOME", "PULSAR", "UBUNTU", "PANTHEON"]) or any(k in session for k in ["GNOME", "PULSAR", "UBUNTU", "PANTHEON"]):
        return True
    try:
        res = subprocess.run(["pgrep", "-x", "gnome-shell"], capture_output=True)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    return False

class GnomeExtensionsWidget(Gtk.Box):
    """Integrated GNOME Extensions manager: manage local extensions & browse extensions.gnome.org (EGO)."""

    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.main_window = main_window
        self.installed_extensions = []
        self.ego_search_results = []

        self.setup_ui()
        self.load_installed_extensions()

    def setup_ui(self):
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(20)
        self.set_margin_end(20)

        # Header Bar
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_lbl = Gtk.Label(label=_("Extensiones GNOME"), xalign=0)
        title_lbl.add_css_class("store-section-title")
        sub_lbl = Gtk.Label(label=_("Administra extensiones del sistema y descubre novedades en extensions.gnome.org"), xalign=0)
        sub_lbl.add_css_class("subtitle-label")
        title_box.append(title_lbl)
        title_box.append(sub_lbl)
        title_box.set_hexpand(True)
        header_box.append(title_box)

        # Tab Switcher Buttons (Installed vs EGO Store)
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_box.add_css_class("linked")
        tab_box.set_valign(Gtk.Align.CENTER)

        self.tab_installed_btn = Gtk.Button(label=_("Instaladas"))
        self.tab_installed_btn.add_css_class("suggested-action")
        self.tab_installed_btn.add_css_class("compact-tab-btn")
        self.tab_installed_btn.set_valign(Gtk.Align.CENTER)
        self.tab_installed_btn.connect("clicked", lambda b: self.switch_tab("installed"))
        tab_box.append(self.tab_installed_btn)

        self.tab_ego_btn = Gtk.Button(label=_("Explorar EGO"))
        self.tab_ego_btn.add_css_class("compact-tab-btn")
        self.tab_ego_btn.set_valign(Gtk.Align.CENTER)
        self.tab_ego_btn.connect("clicked", lambda b: self.switch_tab("ego"))
        tab_box.append(self.tab_ego_btn)

        header_box.append(tab_box)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Recargar"))
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda b: self.refresh_active_tab())
        header_box.append(refresh_btn)

        self.append(header_box)

        # Stack for tabs
        self.tab_stack = Gtk.Stack()
        self.tab_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.tab_stack.set_vexpand(True)
        self.tab_stack.set_hexpand(True)

        # Tab 1: Installed Extensions
        self.installed_page = self.setup_installed_tab()
        self.tab_stack.add_named(self.installed_page, "installed")

        # Tab 2: EGO Browser
        self.ego_page = self.setup_ego_tab()
        self.tab_stack.add_named(self.ego_page, "ego")

        self.append(self.tab_stack)

    def switch_tab(self, tab_name):
        self.tab_stack.set_visible_child_name(tab_name)
        if tab_name == "installed":
            self.tab_installed_btn.add_css_class("suggested-action")
            self.tab_ego_btn.remove_css_class("suggested-action")
            self.load_installed_extensions()
        else:
            self.tab_ego_btn.add_css_class("suggested-action")
            self.tab_installed_btn.remove_css_class("suggested-action")
            if not self.ego_search_results:
                self.search_ego("")

    def refresh_active_tab(self):
        if self.tab_stack.get_visible_child_name() == "installed":
            self.load_installed_extensions()
        else:
            self.search_ego(self.ego_search_entry.get_text().strip())

    # ── TAB 1: INSTALLED EXTENSIONS ──────────────────────────────────────────

    def setup_installed_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_vexpand(True)

        # Filter Entry
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.installed_search_entry = Gtk.SearchEntry()
        self.installed_search_entry.set_placeholder_text(_("Filtrar extensiones instaladas..."))
        self.installed_search_entry.set_hexpand(True)
        self.installed_search_entry.connect("search-changed", self._on_installed_filter_changed)
        search_box.append(self.installed_search_entry)
        box.append(search_box)

        # List Container
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.installed_scrolled = scrolled

        self.installed_listbox = Gtk.ListBox()
        self.installed_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.installed_listbox.add_css_class("card")
        scrolled.set_child(self.installed_listbox)
        box.append(scrolled)

        return box

    def load_installed_extensions(self):
        def worker():
            exts = self._query_installed_extensions()
            GLib.idle_add(self._on_installed_loaded, exts)

        threading.Thread(target=worker, daemon=True).start()

    def _query_installed_extensions(self):
        exts_map = {}
        
        # 1. Query enabled extensions
        enabled_uuids = set()
        if shutil.which("gnome-extensions"):
            try:
                res = subprocess.run(["gnome-extensions", "list", "--enabled"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if line:
                            enabled_uuids.add(line)
            except Exception:
                pass

        # 2. Search extension paths (user paths first so they take precedence)
        search_dirs = [
            (os.path.expanduser("~/.local/share/gnome-shell/extensions"), "user"),
            ("/usr/share/gnome-shell/extensions", "system"),
            ("/usr/local/share/gnome-shell/extensions", "system")
        ]

        for base_dir, ext_type in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                ext_dir = os.path.join(base_dir, entry)
                if not os.path.isdir(ext_dir):
                    continue
                meta_path = os.path.join(ext_dir, "metadata.json")
                if not os.path.isfile(meta_path):
                    continue
                
                try:
                    with open(meta_path, "r", encoding="utf-8", errors="ignore") as f:
                        meta = json.load(f)
                    
                    uuid = meta.get("uuid", entry)
                    if uuid in exts_map:
                        continue

                    name = meta.get("name", uuid)
                    desc = meta.get("description", "")
                    version = str(meta.get("version", ""))
                    has_prefs = (
                        os.path.exists(os.path.join(ext_dir, "prefs.js")) or 
                        os.path.exists(os.path.join(ext_dir, "prefs.ui"))
                    )
                    state = "ENABLED" if uuid in enabled_uuids else "DISABLED"

                    exts_map[uuid] = {
                        "uuid": uuid,
                        "name": name,
                        "description": desc,
                        "state": state,
                        "version": version,
                        "type": ext_type,
                        "has_prefs": has_prefs,
                        "supported_versions": meta.get("shell-version", [])
                    }
                except Exception as e:
                    print(f"Error reading extension metadata {meta_path}: {e}")

        return sorted(exts_map.values(), key=lambda x: x["name"].lower())

    def _on_installed_loaded(self, exts):
        self.installed_extensions = exts
        self.render_installed_list()

    def _on_installed_filter_changed(self, entry):
        self.render_installed_list()

    def render_installed_list(self):
        v_adj = 0.0
        if hasattr(self, 'installed_scrolled') and self.installed_scrolled:
            adj = self.installed_scrolled.get_vadjustment()
            if adj:
                v_adj = adj.get_value()

        while True:
            row = self.installed_listbox.get_first_child()
            if not row:
                break
            self.installed_listbox.remove(row)

        filter_text = self.installed_search_entry.get_text().strip().lower()
        count = 0

        for ext in self.installed_extensions:
            if filter_text:
                if filter_text not in ext["name"].lower() and filter_text not in ext["uuid"].lower() and filter_text not in ext["description"].lower():
                    continue

            row = self.create_installed_row(ext)
            self.installed_listbox.append(row)
            count += 1

        if count == 0:
            empty_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty_row.set_margin_top(24); empty_row.set_margin_bottom(24)
            empty_lbl = Gtk.Label(label=_("No se encontraron extensiones instaladas."))
            empty_lbl.add_css_class("subtitle-label")
            empty_row.append(empty_lbl)
            self.installed_listbox.append(empty_row)

        if v_adj > 0 and hasattr(self, 'installed_scrolled') and self.installed_scrolled:
            GLib.idle_add(lambda: self.installed_scrolled.get_vadjustment().set_value(v_adj))

    def create_installed_row(self, ext):
        row = Adw.ExpanderRow()
        row.set_title(ext["name"])
        row.set_subtitle(ext["uuid"])

        # Prefix Icon
        icon = Gtk.Image.new_from_icon_name("application-x-addon-symbolic")
        icon.set_pixel_size(24)
        row.add_prefix(icon)

        # Header Badges (Version, Compatibility & Type)
        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        badge_box.set_valign(Gtk.Align.CENTER)

        if ext["version"]:
            v_badge = Gtk.Label(label=f"v{ext['version']}")
            v_badge.add_css_class("badge")
            v_badge.add_css_class("badge-generic")
            badge_box.append(v_badge)

        from src.utils.system import check_gnome_shell_compatibility
        is_comp, badge_text, tooltip = check_gnome_shell_compatibility(ext.get("supported_versions", []))
        c_badge = Gtk.Label(label=badge_text)
        c_badge.add_css_class("badge")
        c_badge.add_css_class("badge-success" if is_comp else "badge-warning")
        if tooltip:
            c_badge.set_tooltip_text(tooltip)
        badge_box.append(c_badge)

        t_badge = Gtk.Label(label="Sistema" if ext["type"] == "system" else "Usuario")
        t_badge.add_css_class("badge")
        t_badge.add_css_class("badge-system" if ext["type"] == "system" else "badge-flatpak")
        badge_box.append(t_badge)

        row.add_suffix(badge_box)

        # Enable/Disable Switch on the header row
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        is_enabled = (ext["state"] == "ENABLED")
        switch.set_active(is_enabled)
        
        # State label in info grid (to update on toggle without rebuild)
        state_val = Gtk.Label(label=ext.get("state", "DESCONOCIDO"), xalign=0)
        switch.connect("state-set", self._on_extension_toggle, ext["uuid"], state_val)
        row.add_suffix(switch)

        # --- EXPANDED DETAILS ---
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        details_box.set_margin_top(12)
        details_box.set_margin_bottom(12)
        details_box.set_margin_start(16)
        details_box.set_margin_end(16)

        # Full Description
        if ext.get("description"):
            desc_lbl = Gtk.Label(label=ext["description"], xalign=0)
            desc_lbl.add_css_class("subtitle-label")
            desc_lbl.set_wrap(True)
            details_box.append(desc_lbl)

        # Metadata info grid
        info_grid = Gtk.Grid()
        info_grid.set_column_spacing(16)
        info_grid.set_row_spacing(6)

        uuid_title = Gtk.Label(label=_("Identificador:"), xalign=0)
        uuid_title.add_css_class("caption")
        uuid_val = Gtk.Label(label=ext["uuid"], xalign=0)
        uuid_val.set_selectable(True)
        info_grid.attach(uuid_title, 0, 0, 1, 1)
        info_grid.attach(uuid_val, 1, 0, 1, 1)

        state_title = Gtk.Label(label=_("Estado:"), xalign=0)
        state_title.add_css_class("caption")
        info_grid.attach(state_title, 0, 1, 1, 1)
        info_grid.attach(state_val, 1, 1, 1, 1)

        details_box.append(info_grid)

        # Error / Diagnosis message box (hidden by default)
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        error_box.add_css_class("card")
        error_box.set_visible(False)
        error_lbl = Gtk.Label(label="", xalign=0)
        error_lbl.set_wrap(True)
        error_lbl.set_selectable(True)
        error_box.append(error_lbl)
        details_box.append(error_box)

        # Bottom Action buttons row with descriptive text
        actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions_row.set_margin_top(6)
        actions_row.set_valign(Gtk.Align.CENTER)

        # 1. Preferences button
        if ext["has_prefs"]:
            prefs_btn = Gtk.Button()
            prefs_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            prefs_hbox.append(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
            prefs_hbox.append(Gtk.Label(label=_("Configuración")))
            prefs_btn.set_child(prefs_hbox)
            prefs_btn.add_css_class("secondary-button")
            prefs_btn.connect("clicked", lambda b, u=ext["uuid"]: self._open_extension_prefs(u))
            actions_row.append(prefs_btn)

        # 2. Diagnosis & errors button
        diag_btn = Gtk.Button()
        diag_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        diag_hbox.append(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
        diag_hbox.append(Gtk.Label(label=_("Diagnóstico")))
        diag_btn.set_child(diag_hbox)
        diag_btn.add_css_class("flat")
        diag_btn.connect("clicked", self._on_show_extension_diagnosis, ext["uuid"], error_box, error_lbl)
        actions_row.append(diag_btn)

        # 2.5 Details button
        details_btn = Gtk.Button()
        det_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        det_hbox.append(Gtk.Image.new_from_icon_name("document-properties-symbolic"))
        det_hbox.append(Gtk.Label(label=_("Ver detalles")))
        details_btn.set_child(det_hbox)
        details_btn.add_css_class("flat")
        details_btn.connect("clicked", lambda b, u=ext["uuid"]: self.main_window.show_package_details(f"gnome-ext:{u}", is_local=False))
        actions_row.append(details_btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        actions_row.append(spacer)

        # 3. Uninstall button (user extensions only)
        if ext["type"] == "user":
            del_btn = Gtk.Button()
            del_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            del_hbox.append(Gtk.Image.new_from_icon_name("user-trash-symbolic"))
            del_hbox.append(Gtk.Label(label=_("Desinstalar")))
            del_btn.set_child(del_hbox)
            del_btn.add_css_class("destructive-button")
            del_btn.connect("clicked", self._on_uninstall_extension, ext["uuid"])
            actions_row.append(del_btn)

        details_box.append(actions_row)

        content_row = Adw.ActionRow()
        content_row.set_child(details_box)
        row.add_row(content_row)

        return row

    def _open_extension_prefs(self, uuid):
        def worker():
            for base in [os.path.expanduser("~/.local/share/gnome-shell/extensions"), "/usr/share/gnome-shell/extensions"]:
                s_dir = os.path.join(base, uuid, "schemas")
                if os.path.isdir(s_dir):
                    subprocess.run(["glib-compile-schemas", s_dir], capture_output=True)
            res = subprocess.run(["gnome-extensions", "prefs", uuid], capture_output=True)
            if res.returncode != 0:
                subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.LaunchExtensionPrefs", uuid], capture_output=True)

        threading.Thread(target=worker, daemon=True).start()

    def _on_show_extension_diagnosis(self, button, uuid, error_box, error_lbl):
        def worker():
            info_text = ""
            try:
                res = subprocess.run(["gnome-extensions", "info", uuid], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    info_text = res.stdout.strip()
                else:
                    info_text = res.stderr.strip() or _("No se pudo obtener información de la extensión.")
            except Exception as e:
                info_text = f"Error: {e}"

            GLib.idle_add(self._update_diagnosis_ui, error_box, error_lbl, info_text)

        threading.Thread(target=worker, daemon=True).start()

    def _update_diagnosis_ui(self, error_box, error_lbl, info_text):
        error_lbl.set_text(info_text)
        error_box.set_visible(not error_box.get_visible())

    def _on_extension_toggle(self, switch, state, uuid, state_val_label=None):
        new_state_str = "ENABLED" if state else "DISABLED"
        for ext in self.installed_extensions:
            if ext["uuid"] == uuid:
                ext["state"] = new_state_str
                break
        if state_val_label:
            state_val_label.set_text(new_state_str)

        def worker():
            if state:
                for base in [os.path.expanduser("~/.local/share/gnome-shell/extensions"), "/usr/share/gnome-shell/extensions"]:
                    s_dir = os.path.join(base, uuid, "schemas")
                    if os.path.isdir(s_dir):
                        subprocess.run(["glib-compile-schemas", s_dir], capture_output=True)
                subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.ReloadExtension", uuid], capture_output=True)
                subprocess.run(["gnome-extensions", "enable", uuid], capture_output=True)
                subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.EnableExtension", uuid], capture_output=True)
                try:
                    res_en = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], capture_output=True, text=True)
                    if res_en.returncode == 0 and uuid not in res_en.stdout:
                        import ast
                        arr = ast.literal_eval(res_en.stdout.strip())
                        if isinstance(arr, list) and uuid not in arr:
                            arr.append(uuid)
                            subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(arr)], capture_output=True)
                except Exception:
                    pass
            else:
                subprocess.run(["gnome-extensions", "disable", uuid], capture_output=True)
                subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.DisableExtension", uuid], capture_output=True)
                try:
                    res_en = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], capture_output=True, text=True)
                    if res_en.returncode == 0 and uuid in res_en.stdout:
                        import ast
                        arr = ast.literal_eval(res_en.stdout.strip())
                        if isinstance(arr, list) and uuid in arr:
                            arr = [x for x in arr if x != uuid]
                            subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(arr)], capture_output=True)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
        return False

    def _on_uninstall_extension(self, button, uuid):
        def worker():
            user_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{uuid}")
            subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.DisableExtension", uuid], capture_output=True)
            subprocess.run(["gnome-extensions", "disable", uuid], capture_output=True)
            subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions", "--object-path", "/org/gnome/Shell/Extensions", "--method", "org.gnome.Shell.Extensions.UninstallExtension", uuid], capture_output=True)
            subprocess.run(["gnome-extensions", "uninstall", uuid], capture_output=True)
            if os.path.isdir(user_dir):
                shutil.rmtree(user_dir, ignore_errors=True)
            try:
                res_en = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], capture_output=True, text=True)
                if res_en.returncode == 0 and uuid in res_en.stdout:
                    import ast
                    arr = ast.literal_eval(res_en.stdout.strip())
                    if isinstance(arr, list) and uuid in arr:
                        arr = [x for x in arr if x != uuid]
                        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(arr)], capture_output=True)
            except Exception:
                pass
            GLib.idle_add(self.load_installed_extensions)

        threading.Thread(target=worker, daemon=True).start()

    # ── TAB 2: EXPLORE EGO (extensions.gnome.org) ────────────────────────────

    def setup_ego_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_vexpand(True)

        # Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ego_search_entry = Gtk.SearchEntry()
        self.ego_search_entry.set_placeholder_text(_("Buscar en extensions.gnome.org..."))
        self.ego_search_entry.set_hexpand(True)
        self.ego_search_entry.connect("search-changed", self._on_ego_search_changed)
        self.ego_search_entry.connect("activate", self._on_ego_search_activated)
        search_box.append(self.ego_search_entry)
        box.append(search_box)

        # Scrolled FlowBox
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.ego_flowbox = Gtk.FlowBox()
        self.ego_flowbox.set_valign(Gtk.Align.START)
        self.ego_flowbox.set_max_children_per_line(2)
        self.ego_flowbox.set_min_children_per_line(1)
        self.ego_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.ego_flowbox.set_row_spacing(12)
        self.ego_flowbox.set_column_spacing(12)
        self.ego_flowbox.set_homogeneous(True)
        self.ego_flowbox.set_margin_top(8)
        self.ego_flowbox.set_margin_bottom(16)

        scrolled.set_child(self.ego_flowbox)
        box.append(scrolled)

        # Spinner
        self.ego_spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.ego_spinner_box.set_valign(Gtk.Align.CENTER)
        self.ego_spinner_box.set_halign(Gtk.Align.CENTER)
        self.ego_spinner = Gtk.Spinner()
        self.ego_spinner.set_size_request(32, 32)
        self.ego_status_lbl = Gtk.Label(label=_("Buscando en extensions.gnome.org..."))
        self.ego_status_lbl.add_css_class("subtitle-label")
        self.ego_spinner_box.append(self.ego_spinner)
        self.ego_spinner_box.append(self.ego_status_lbl)
        self.ego_spinner_box.set_visible(False)
        box.append(self.ego_spinner_box)

        return box

    def _on_ego_search_changed(self, entry):
        # Debounce or run search
        pass

    def _on_ego_search_activated(self, entry):
        query = entry.get_text().strip()
        self.search_ego(query)

    def search_ego(self, query):
        self.ego_spinner_box.set_visible(True)
        self.ego_spinner.start()
        self.ego_flowbox.set_visible(False)

        def worker():
            url = f"https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(query)}&n_per_page=20"
            req = urllib.request.Request(url, headers={"User-Agent": "AppInstall/1.0"})
            results = []
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    results = data.get("extensions", [])
            except Exception as e:
                print(f"Error querying EGO: {e}")

            GLib.idle_add(self._on_ego_results_loaded, results)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ego_results_loaded(self, results):
        self.ego_spinner.stop()
        self.ego_spinner_box.set_visible(False)
        self.ego_flowbox.set_visible(True)
        self.ego_search_results = results
        self.render_ego_results()

    def render_ego_results(self):
        while True:
            child = self.ego_flowbox.get_first_child()
            if not child:
                break
            self.ego_flowbox.remove(child)

        installed_uuids = {e["uuid"] for e in self.installed_extensions}

        if not self.ego_search_results:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty_box.set_margin_top(32)
            lbl = Gtk.Label(label=_("No se encontraron extensiones en extensions.gnome.org."))
            lbl.add_css_class("subtitle-label")
            empty_box.append(lbl)
            self.ego_flowbox.append(empty_box)
            return

        for ext in self.ego_search_results:
            card = self.create_ego_card(ext, is_installed=(ext.get("uuid") in installed_uuids))
            self.ego_flowbox.append(card)

    def create_ego_card(self, ext, is_installed=False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        card.set_size_request(300, -1)

        # Header Row: Icon + Title + Author
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        from src.utils.system import create_app_icon_widget
        icon_rel = ext.get("icon", "")
        if icon_rel and not icon_rel.endswith("plugin.png"):
            full_icon_url = f"https://extensions.gnome.org{icon_rel}" if icon_rel.startswith("/") else icon_rel
            icon_img = create_app_icon_widget(full_icon_url, size=44, fallback="application-x-addon-symbolic", package_id=f"ego_{ext.get('pk', '0')}")
        else:
            icon_img = create_app_icon_widget("", size=44, fallback="application-x-addon-symbolic")
        icon_img.add_css_class("app-card-icon")

        top_row.append(icon_img)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        name_lbl = Gtk.Label(label=ext.get("name", "Extension"), xalign=0)
        name_lbl.add_css_class("app-card-title")
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(name_lbl)

        author_lbl = Gtk.Label(label=f"por {ext.get('creator', 'EGO')}", xalign=0)
        author_lbl.add_css_class("app-card-subtitle")
        author_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(author_lbl)

        top_row.append(info_box)

        # Badges box in top row (Downloads + Shell Compatibility)
        badges_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        badges_col.set_valign(Gtk.Align.CENTER)
        badges_col.set_halign(Gtk.Align.END)

        from src.utils.system import check_gnome_shell_compatibility
        shell_map = ext.get("shell_version_map", {})
        is_comp, badge_text, tooltip = check_gnome_shell_compatibility(shell_map)
        
        c_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        c_badge.add_css_class("badge")
        c_badge.add_css_class("badge-success" if is_comp else "badge-warning")
        c_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic" if is_comp else "dialog-warning-symbolic")
        c_icon.set_pixel_size(10)
        c_badge.append(c_icon)
        c_lbl = Gtk.Label(label=badge_text)
        c_badge.append(c_lbl)
        if tooltip:
            c_badge.set_tooltip_text(tooltip)
        badges_col.append(c_badge)

        dls = ext.get("downloads", 0)
        if dls:
            try:
                dls_int = int(dls)
                dls_formatted = f"{dls_int:,}".replace(",", ".")
            except Exception:
                dls_formatted = str(dls)
            d_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            d_badge.add_css_class("badge")
            d_badge.add_css_class("badge-generic")
            d_icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
            d_icon.set_pixel_size(10)
            d_badge.append(d_icon)
            d_lbl = Gtk.Label(label=dls_formatted)
            d_badge.append(d_lbl)
            badges_col.append(d_badge)

        top_row.append(badges_col)

        card.append(top_row)

        # Description
        desc_lbl = Gtk.Label(label=ext.get("description", ""), xalign=0)
        desc_lbl.add_css_class("subtitle-label")
        desc_lbl.set_wrap(True)
        desc_lbl.set_lines(2)
        desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        desc_lbl.set_vexpand(True)
        card.append(desc_lbl)

        # Bottom Action Row
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_margin_top(4)

        uuid_lbl = Gtk.Label(label=ext.get("uuid", ""), xalign=0)
        uuid_lbl.add_css_class("subtitle-label")
        uuid_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        uuid_lbl.set_hexpand(True)
        action_row.append(uuid_lbl)

        if is_installed:
            inst_btn = Gtk.Button(label=_("Instalada"))
            inst_btn.add_css_class("app-card-button-secondary")
            inst_btn.set_sensitive(False)
        else:
            inst_btn = Gtk.Button(label=_("Instalar"))
            inst_btn.add_css_class("app-card-button")
            inst_btn.connect("clicked", self._on_install_ego_extension, ext, inst_btn)

        action_row.append(inst_btn)
        card.append(action_row)

        # Make card clickable to view details
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda g, n, x, y: self.main_window.show_package_details(f"gnome-ext:{ext.get('uuid')}", is_local=False))
        card.add_controller(gesture)

        return card

    def _on_install_ego_extension(self, button, ext, btn_widget):
        uuid = ext.get("uuid")
        if uuid:
            self.main_window.install_package_by_identifier(f"gnome-ext:{uuid}")
            btn_widget.set_sensitive(True)
