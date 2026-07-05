import os
from gi.repository import Gtk, GLib, Adw
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size

class AppImageConfigWindow(Adw.Window):
    def __init__(self, parent, file_path, callback):
        super().__init__()
        self.set_title(_("Configurar AppImage"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(450, 400, 0.8)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")
        
        self.file_path = file_path
        self.callback = callback
        
        # Nombre por defecto basado en el archivo
        filename = os.path.basename(file_path)
        self.default_name = os.path.splitext(filename)[0]
        
        # Icono por defecto de App Install
        local_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.icon_path = os.path.join(local_dir, "appimage.png")

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Configurar AppImage")))
        header_bar.add_css_class("header-bar")

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        toolbar_view.set_content(main_box)

        # Name section
        name_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_section.add_css_class("card")
        name_label = Gtk.Label(label=_("¿Cómo quieres llamar a la app?"), xalign=0)
        name_label.add_css_class("title-label")
        name_section.append(name_label)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(self.default_name)
        self.name_entry.set_placeholder_text(_("Escribe el nombre de la aplicación..."))
        name_section.append(self.name_entry)
        main_box.append(name_section)

        # Icon section
        icon_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon_section.add_css_class("card")
        icon_title = Gtk.Label(label=_("Ponle un icono chulo"), xalign=0)
        icon_title.add_css_class("title-label")
        icon_section.append(icon_title)
        
        icon_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.icon_image = Gtk.Image.new_from_file(self.icon_path)
        self.icon_image.set_pixel_size(64)
        icon_hbox.append(self.icon_image)
        
        icon_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.icon_label = Gtk.Label(label=_("Icono por defecto"), xalign=0)
        self.icon_label.add_css_class("subtitle-label")
        icon_vbox.append(self.icon_label)
        
        select_icon_button = Gtk.Button()
        select_icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        select_icon_icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        select_icon_box.prepend(select_icon_icon)
        select_icon_text = Gtk.Label(label=_("Seleccionar icono..."))
        select_icon_box.append(select_icon_text)
        select_icon_button.set_child(select_icon_box)
        select_icon_button.connect("clicked", self.on_select_icon_clicked)
        icon_vbox.append(select_icon_button)
        icon_hbox.append(icon_vbox)
        icon_section.append(icon_hbox)
        main_box.append(icon_section)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_button = Gtk.Button(label=_("Cancelar"))
        cancel_button.connect("clicked", lambda x: self.close())
        button_box.append(cancel_button)
        
        self.install_button = Gtk.Button()
        self.install_button.add_css_class("action-button")
        install_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        install_box.prepend(install_icon)
        install_label = Gtk.Label(label=_("¡Instalar!"))
        install_box.append(install_label)
        self.install_button.set_child(install_box)
        self.install_button.connect("clicked", self.on_install_clicked)
        button_box.append(self.install_button)
        main_box.append(button_box)

    def on_select_icon_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar icono para la aplicación"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        filter_img = Gtk.FileFilter()
        filter_img.set_name(_("Archivos de imagen"))
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        filter_img.add_mime_type("image/svg+xml")
        dialog.add_filter(filter_img)
        dialog.connect("response", self._on_icon_dialog_response)
        dialog.show()

    def _on_icon_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.icon_path = file.get_path()
                self.icon_image.set_from_file(self.icon_path)
                self.icon_label.set_text(os.path.basename(self.icon_path))
        dialog.destroy()

    def on_install_clicked(self, button):
        custom_name = self.name_entry.get_text().strip()
        if not custom_name: custom_name = self.default_name
        self.callback(custom_name, self.icon_path)
        self.close()
