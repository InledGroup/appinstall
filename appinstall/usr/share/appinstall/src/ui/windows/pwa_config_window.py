import os
import threading
import requests
from gi.repository import Gtk, GLib, Adw
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size

class PWAConfigWindow(Adw.Window):
    def __init__(self, parent, callback):
        super().__init__()
        self.set_title(_("Crear PWA (Web App)"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(450, 500, 0.8)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")
        
        self.callback = callback
        # Use a more reliable way to find the default icon
        local_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.icon_path = os.path.join(local_dir, "appimage.png")

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Crear PWA")))
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

        # URL section
        url_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        url_section.add_css_class("card")
        url_label = Gtk.Label(label=_("Introduce la URL de la web"), xalign=0)
        url_label.add_css_class("title-label")
        url_section.append(url_label)
        
        url_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text(_("https://ejemplo.com"))
        self.url_entry.set_hexpand(True)
        url_hbox.append(self.url_entry)
        
        fetch_button = Gtk.Button()
        fetch_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        fetch_button.set_child(fetch_icon)
        fetch_button.connect("clicked", self.on_fetch_clicked)
        url_hbox.append(fetch_button)
        url_section.append(url_hbox)
        main_box.append(url_section)

        # Info section
        self.info_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.info_section.set_sensitive(False)
        
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_box.add_css_class("card")
        name_label = Gtk.Label(label=_("Nombre de la aplicación"), xalign=0)
        name_label.add_css_class("title-label")
        name_box.append(name_label)
        self.name_entry = Gtk.Entry()
        name_box.append(self.name_entry)
        self.info_section.append(name_box)
        
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon_box.add_css_class("card")
        icon_label = Gtk.Label(label=_("Icono"), xalign=0)
        icon_label.add_css_class("title-label")
        icon_box.append(icon_label)
        
        icon_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.icon_image = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        self.icon_image.set_pixel_size(64)
        icon_hbox.append(self.icon_image)
        
        change_icon_button = Gtk.Button(label=_("Cambiar icono..."))
        change_icon_button.connect("clicked", self.on_change_icon_clicked)
        change_icon_button.set_valign(Gtk.Align.CENTER)
        icon_hbox.append(change_icon_button)
        icon_box.append(icon_hbox)
        self.info_section.append(icon_box)
        main_box.append(self.info_section)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.set_halign(Gtk.Align.CENTER)
        main_box.append(self.spinner)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_button = Gtk.Button(label=_("Cancelar"))
        cancel_button.connect("clicked", lambda x: self.close())
        button_box.append(cancel_button)
        
        self.create_button = Gtk.Button()
        self.create_button.add_css_class("action-button")
        create_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        create_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        create_box.prepend(create_icon)
        create_label = Gtk.Label(label=_("¡Crear PWA!"))
        create_box.append(create_label)
        self.create_button.set_child(create_box)
        self.create_button.connect("clicked", self.on_create_clicked)
        self.create_button.set_sensitive(False)
        button_box.append(self.create_button)
        main_box.append(button_box)

    def on_fetch_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url: return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_entry.set_text(url)
        self.spinner.start()
        self.spinner.set_visible(True)
        self.info_section.set_sensitive(False)
        thread = threading.Thread(target=self.fetch_info_thread, args=(url,))
        thread.daemon = True
        thread.start()

    def fetch_info_thread(self, url):
        try:
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            title = ""
            if response.status_code == 200:
                import re
                match = re.search('<title>(.*?)</title>', response.text, re.IGNORECASE)
                if match: title = match.group(1).strip()
            if not title:
                from urllib.parse import urlparse
                title = urlparse(url).netloc.replace("www.", "")

            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            icon_temp_path = os.path.join(os.path.expanduser("~/.cache/appinstall"), f"pwa_{domain}.png")
            os.makedirs(os.path.dirname(icon_temp_path), exist_ok=True)
            
            icon_response = requests.get(favicon_url, timeout=10)
            if icon_response.status_code == 200:
                with open(icon_temp_path, 'wb') as f: f.write(icon_response.content)
                icon_to_use = icon_temp_path
            else:
                icon_to_use = self.icon_path

            GLib.idle_add(self.on_info_fetched, title, icon_to_use)
        except Exception as e:
            print(f"Error fetching PWA info: {e}")
            GLib.idle_add(self.on_info_fetched, "", self.icon_path)

    def on_info_fetched(self, title, icon_path):
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.info_section.set_sensitive(True)
        self.create_button.set_sensitive(True)
        if title: self.name_entry.set_text(title)
        self.icon_path = icon_path
        self.icon_image.set_from_file(icon_path)
        return False

    def on_change_icon_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar icono para la PWA"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        dialog.connect("response", self._on_icon_dialog_response)
        dialog.show()

    def _on_icon_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.icon_path = file.get_path()
                self.icon_image.set_from_file(self.icon_path)
        dialog.destroy()

    def on_create_clicked(self, button):
        name = self.name_entry.get_text().strip()
        url = self.url_entry.get_text().strip()
        if name and url:
            self.callback(name, url, self.icon_path)
            self.close()
