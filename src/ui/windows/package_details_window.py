import os
from gi.repository import Gtk, Adw, GLib, Gdk
from src.infrastructure.services.localization import _

class PackageDetailsWindow(Adw.Window):
    def __init__(self, parent, info, on_install_callback):
        super().__init__()
        self.set_title(_("Detalles de la aplicación"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 600)
        self.add_css_class("main-window")
        
        self.info = info
        self.on_install_callback = on_install_callback

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.add_css_class("header-bar")
        
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar_view.set_content(scrolled)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(32)
        main_box.set_margin_bottom(32)
        main_box.set_margin_start(32)
        main_box.set_margin_end(32)
        scrolled.set_child(main_box)

        # 1. Top Section: Icon and Title
        top_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        top_hbox.set_halign(Gtk.Align.CENTER)
        
        # Icon
        icon_path = info.get('icon')
        if icon_path and os.path.exists(icon_path):
            icon_image = Gtk.Image.new_from_file(icon_path)
        else:
            # Fallback to generic icon if extraction failed
            ext = info.get('ext', '')
            if ext == 'deb': icon_name = "package-x-generic"
            elif ext == 'rpm': icon_name = "package-x-generic"
            elif ext == 'appimage': icon_name = "application-x-executable"
            else: icon_name = "package-x-generic-symbolic"
            icon_image = Gtk.Image.new_from_icon_name(icon_name)
        
        icon_image.set_pixel_size(128)
        top_hbox.append(icon_image)
        main_box.append(top_hbox)

        # Title and Version
        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_vbox.set_halign(Gtk.Align.CENTER)
        
        name_label = Gtk.Label(label=info.get('name', 'App'), xalign=0.5)
        name_label.set_css_classes(["title-1"])
        name_label.set_wrap(True)
        name_label.set_justify(Gtk.Justification.CENTER)
        title_vbox.append(name_label)
        
        version_label = Gtk.Label(label=info.get('version', ''), xalign=0.5)
        version_label.add_css_class("subtitle-label")
        title_vbox.append(version_label)
        main_box.append(title_vbox)

        # 2. Action Button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        btn_box.set_halign(Gtk.Align.CENTER)
        install_button = Gtk.Button(label=_("Instalar"))
        install_button.add_css_class("suggested-action")
        install_button.add_css_class("pill")
        install_button.set_size_request(200, 48)
        install_button.connect("clicked", self.on_install_clicked)
        btn_box.append(install_button)
        main_box.append(btn_box)

        # Separator
        main_box.append(Gtk.Separator())

        # 3. Description Section
        desc_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        desc_title = Gtk.Label(label=_("Información"), xalign=0)
        desc_title.add_css_class("title-label")
        desc_section.append(desc_title)
        
        desc_text = Gtk.Label(label=info.get('description', ''), xalign=0)
        desc_text.set_wrap(True)
        desc_text.set_max_width_chars(60)
        desc_section.append(desc_text)
        main_box.append(desc_section)

        # 4. Technical Details Section (Grid style)
        details_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        details_card.add_css_class("card")
        
        details_title = Gtk.Label(label=_("Detalles técnicos"), xalign=0)
        details_title.add_css_class("title-label")
        details_card.append(details_title)
        
        details_grid = Gtk.Grid()
        details_grid.set_column_spacing(24)
        details_grid.set_row_spacing(8)
        
        # Size
        details_grid.attach(Gtk.Label(label=_("Tamaño de instalación"), xalign=1), 0, 0, 1, 1)
        details_grid.attach(Gtk.Label(label=info.get('size', 'N/A'), xalign=0), 1, 0, 1, 1)
        
        # Package format
        ext = "N/A"
        if 'ext' in info: ext = info['ext']
        details_grid.attach(Gtk.Label(label=_("Formato"), xalign=1), 0, 1, 1, 1)
        details_grid.attach(Gtk.Label(label=ext.upper(), xalign=0), 1, 1, 1, 1)
        
        details_card.append(details_grid)
        main_box.append(details_card)

        # 5. Permissions Section
        permissions_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        permissions_card.add_css_class("card")
        
        perm_title = Gtk.Label(label=_("Permisos"), xalign=0)
        perm_title.add_css_class("title-label")
        permissions_card.append(perm_title)
        
        # Native apps usually have full access
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
        self.close()
        self.on_install_callback()
