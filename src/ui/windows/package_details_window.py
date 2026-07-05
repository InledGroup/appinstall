import os
import re
from gi.repository import Gtk, Adw, GLib, Gdk
from src.infrastructure.services.localization import _

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    # Replace list items with bullets
    text = re.sub(r'<li>\s*', '• ', raw_html)
    # Replace paragraphs and line breaks
    text = re.sub(r'</p>|<br\s*/?>', '\n\n', text)
    # Strip all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode XML/HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
    # Clean up double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

class PackageDetailsWidget(Gtk.Box):
    def __init__(self, parent_window, info, on_install_callback, on_uninstall_callback, back_callback):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.parent_window = parent_window
        self.on_install_callback = on_install_callback
        self.on_uninstall_callback = on_uninstall_callback
        self.back_callback = back_callback
        self.add_css_class("main-window")
        
        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(False)
        header_bar.set_show_start_title_buttons(False)
        header_bar.set_title_widget(Adw.WindowTitle(title=info.get('name', '')))
        header_bar.add_css_class("header-bar")
        
        back_btn = Gtk.Button()
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", lambda b: self.back_callback())
        header_bar.pack_start(back_btn)
        
        # ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.append(toolbar_view)
        
        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        toolbar_view.set_content(scrolled)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        scrolled.set_child(main_box)

        # 1. Header Card (Icon + Title + Version + Developer)
        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_vbox.set_halign(Gtk.Align.CENTER)
        
        # Icon
        icon_path = info.get('icon')
        if icon_path and os.path.exists(icon_path):
            icon_image = Gtk.Image.new_from_file(icon_path)
        else:
            icon_name = icon_path if icon_path else "system-software-install-symbolic"
            icon_image = Gtk.Image.new_from_icon_name(icon_name)
        
        icon_image.set_pixel_size(96)
        icon_image.set_halign(Gtk.Align.CENTER)
        title_vbox.append(icon_image)
        
        title_label = Gtk.Label(label=info.get('name', ''), xalign=0.5)
        title_label.add_css_class("title-label")
        title_label.set_wrap(True)
        title_label.set_max_width_chars(30)
        title_vbox.append(title_label)
        
        version_label = Gtk.Label(label=info.get('version', ''), xalign=0.5)
        version_label.add_css_class("subtitle-label")
        title_vbox.append(version_label)
        
        developer = info.get('developer', '')
        if developer:
            dev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            dev_box.set_halign(Gtk.Align.CENTER)
            
            dev_label = Gtk.Label(label=developer)
            dev_label.add_css_class("subtitle-label")
            dev_box.append(dev_label)
            
            if info.get('verified'):
                verified_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                verified_icon.set_tooltip_text(_("Autor verificado"))
                verified_icon.add_css_class("verified-icon")
                dev_box.append(verified_icon)
                
            title_vbox.append(dev_box)
            
        main_box.append(title_vbox)

        # 2. Action Button
        action_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        action_btn_box.set_halign(Gtk.Align.CENTER)
        
        self.is_installed = info.get('is_installed', False)
        if self.is_installed:
            self.install_btn = Gtk.Button(label=_("Desinstalar"))
            self.install_btn.add_css_class("destructive-action")
            self.install_btn.connect("clicked", self.on_uninstall_clicked)
        else:
            self.install_btn = Gtk.Button(label=_("Instalar"))
            self.install_btn.add_css_class("suggested-action")
            self.install_btn.connect("clicked", self.on_install_clicked)
            
        action_btn_box.append(self.install_btn)
        main_box.append(action_btn_box)

        # 3. Description Card
        desc_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        desc_section.add_css_class("card")
        
        desc_title = Gtk.Label(label=_("Información"), xalign=0)
        desc_title.add_css_class("title-label")
        desc_section.append(desc_title)
        
        desc_text = Gtk.Label(label=clean_html(info.get('description', '')), xalign=0)
        desc_text.set_wrap(True)
        desc_text.set_max_width_chars(60)
        desc_section.append(desc_text)
        
        main_box.append(desc_section)

        # 4. Technical Details Card
        details_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        details_card.add_css_class("card")
        
        details_title = Gtk.Label(label=_("Detalles técnicos"), xalign=0)
        details_title.add_css_class("title-label")
        details_card.append(details_title)
        
        details_grid = Gtk.Grid()
        details_grid.set_column_spacing(24)
        details_grid.set_row_spacing(10)
        
        # Package size
        details_grid.attach(Gtk.Label(label=_("Tamaño instalado"), xalign=1), 0, 0, 1, 1)
        details_grid.attach(Gtk.Label(label=info.get('size', 'N/A'), xalign=0), 1, 0, 1, 1)
        
        # Package format
        ext = "N/A"
        if 'ext' in info: ext = info['ext']
        if info.get('source') in ['flatpak', 'snap', 'aur', 'brew']:
            ext = info['source']
        details_grid.attach(Gtk.Label(label=_("Formato"), xalign=1), 0, 1, 1, 1)
        details_grid.attach(Gtk.Label(label=ext.upper(), xalign=0), 1, 1, 1, 1)

        # Dependencies
        deps = info.get('dependencies', [])
        if deps:
            if isinstance(deps, list):
                display_deps = ", ".join(deps[:15])
                if len(deps) > 15:
                    display_deps += f" ... y {len(deps) - 15} más"
            else:
                display_deps = str(deps)
        else:
            display_deps = _("Ninguna")
            
        deps_label = Gtk.Label(label=display_deps, xalign=0)
        deps_label.set_wrap(True)
        deps_label.set_max_width_chars(45)
        
        details_grid.attach(Gtk.Label(label=_("Dependencias"), xalign=1), 0, 2, 1, 1)
        details_grid.attach(deps_label, 1, 2, 1, 1)
        
        details_card.append(details_grid)
        main_box.append(details_card)

        # 5. Permissions Section
        permissions_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        permissions_card.add_css_class("card")
        
        perm_title = Gtk.Label(label=_("Permisos"), xalign=0)
        perm_title.add_css_class("title-label")
        permissions_card.append(perm_title)
        
        perm_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        perm_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        perm_hbox.append(perm_icon)
        
        perm_text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        perm_main = Gtk.Label(label=_("Acceso total al sistema"), xalign=0)
        perm_main.add_css_class("title-label")
        perm_text_vbox.append(perm_main)
        perm_sub = Gtk.Label(label=_("Como paquete nativo, esta aplicación puede acceder a tus archivos y hardware."), xalign=0)
        perm_sub.add_css_class("subtitle-label")
        perm_sub.set_wrap(True)
        perm_text_vbox.append(perm_sub)
        
        perm_hbox.append(perm_text_vbox)
        permissions_card.append(perm_hbox)
        main_box.append(permissions_card)

    def on_install_clicked(self, button):
        self.on_install_callback()

    def on_uninstall_clicked(self, button):
        self.on_uninstall_callback()
